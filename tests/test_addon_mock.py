"""The LS01 add-on (blender/renou_blsync) against the mock UE receiver: no UE, no team assets.
    blender -b --factory-startup --python-exit-code 1 --python tests/test_addon_mock.py -- build
Background Blender has no event loop, so the test calls the timer callback (live.tick) itself; everything else - the
depsgraph handler, the operators, the worker thread - runs as it does in the UI."""
import json, subprocess, sys, time, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "blender"))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
build = Path(argv[0] if argv else ROOT / "build").resolve()
fx, out = build / "fixture", build / f"addon_{int(time.time())}"
subprocess.run([sys.executable, str(ROOT / "tests" / "make_fixture.py"), str(fx)], check=True)
out.mkdir(parents=True, exist_ok=True)
P, G = fx / "test_01_placements.json", fx / "test_01_parts.glb"
OV, ST = out / "test_01_overrides.json", out / "status.json"
mock = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mock_ue_receiver.py"),
                         "--placements", str(P), "--overrides", str(OV), "--status", str(ST)])

import bpy                                   # noqa: E402
import renou_blsync                          # noqa: E402
from renou_blsync import live, state         # noqa: E402

fails = []


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {info}" if info != "" else ""))
    if not cond:
        fails.append(name)


def settle(timeout=8.0):
    """run the timer by hand until the worker has delivered and the receipt is in."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        live.tick()
        if not state.DIRTY and live.WORKER is not None and live.WORKER.idle():
            live.collect_results()
            return state.RESULTS.get("test_01") or {}
        time.sleep(0.05)
    return state.RESULTS.get("test_01") or {}


def overrides():
    return json.loads(OV.read_text(encoding="utf-8"))


try:
    renou_blsync.register()
    s = bpy.context.scene.renou_sync
    s.placements, s.parts_glb, s.out, s.status = str(P), str(G), str(OV), str(ST)
    s.writeback_dir = str(out / "write_back")
    check("attach operator", bpy.ops.renou.attach() == {"FINISHED"})
    B = state.BATCHES["test_01"]
    check("attach: 26 instances, part meshes loaded", len(B.obj) == 26 and len(B.meshes) == 5, (len(B.obj), len(B.meshes)))

    s.live = True                                   # the panel toggle: starts the timer and the worker
    check("live switch on", state.LIVE and bpy.app.timers.is_registered(live.tick))
    r = settle()
    check("switching on publishes once, receipt back", (r.get("ue") or {}).get("rev") == r.get("rev") and r.get("overrides") == 0, r)

    o = B.group("BLD_01")[0]
    o.location.x += 5.0                             # a hand / script edit; nothing calls publish
    bpy.context.view_layer.update()
    check("depsgraph handler marks the batch dirty", "test_01" in state.DIRTY, state.DIRTY)
    r = settle()
    check("move goes out by itself, UE counts 1 moved", ((r.get("ue") or {}).get("counts") or {}).get("moved") == 1, r.get("ue"))

    src = B.group("BLD_02")[0]
    dup = src.copy()                                # what Shift+D does: the copy carries the same blsync_id
    B.col.objects.link(dup)
    dup.location.y += 30.0
    bpy.context.view_layer.update()
    r = settle()
    ov = overrides()
    check("Shift+D copy gets its own id", dup["blsync_id"] != src["blsync_id"] and dup["blsync_id"] in ov["instances"],
          dup["blsync_id"])
    check("Shift+D: the original keeps its id and stays in place", src["blsync_id"] not in ov["instances"])
    check("Shift+D: receipt counts 1 added", ((r.get("ue") or {}).get("counts") or {}).get("added") == 1, r.get("ue"))

    gone = B.group("BLD_03")[0]
    gone_id = gone["blsync_id"]
    bpy.data.objects.remove(gone)                   # X in the viewport
    bpy.context.view_layer.update()
    r = settle()
    check("deleting an object outright publishes a deletion", overrides()["instances"].get(gone_id) == {"deleted": True})

    pa = B.group("BLD_04")[0]                       # PBOX_A: geometry tag without a real change
    pa.data.update()
    pd = next(x for x in B.col.objects if x.get("blsync_part") == "PBOX_D")
    pd.data.vertices[0].co.z += 1.0                 # a real edit of the part every PBOX_D instance uses
    pd.data.update()
    bpy.context.view_layer.update()
    r = settle()
    m = overrides().get("meshes", {})
    check("real mesh edit: only that part exported", list(m) == ["PBOX_D"], list(m))
    check("mesh edit: receipt without errors", (r.get("ue") or {}).get("rev") == r.get("rev") and not (r.get("ue") or {}).get("errors"), r.get("ue"))

    check("write-back operator", bpy.ops.renou.write_back() == {"FINISHED"})
    tab = json.loads(next((out / "write_back").glob("test_01_placements_v*.json")).read_text(encoding="utf-8"))
    check("write-back: 26 - 1 deleted + 1 added = 26 rows", tab["count"] == 26, tab["count"])

    s.live = False
    check("live switch off stops the timer", not state.LIVE and not bpy.app.timers.is_registered(live.tick))
    o.location.x += 50.0
    bpy.context.view_layer.update()
    rev_before = state.RESULTS["test_01"]["rev"]
    live.tick()
    time.sleep(0.3)
    live.collect_results()
    check("paused: edits are not published", state.RESULTS["test_01"]["rev"] == rev_before)

    check("reset operator", bpy.ops.renou.reset() == {"FINISHED"})
    r = settle()
    check("reset: back to the table, deleted object restored, no overrides",
          r.get("overrides") == 0 and gone_id in B.col.objects and not overrides()["instances"], r.get("overrides"))

    # user 10-10: what 全部还原 cleared is kept; the panel lists it; one click brings it back; attaching again goes on
    snaps = state.snapshots("test_01")
    check("全部还原 left a snapshot the panel lists", snaps and snaps[0]["reason"] == "cleared" and snaps[0]["instances"] >= 3,
          snaps[:1])
    kept = json.loads(Path(snaps[0]["path"]).read_text(encoding="utf-8"))
    check("restore operator", bpy.ops.renou.restore_snapshot(batch="test_01", path=snaps[0]["path"]) == {"FINISHED"})
    r = settle()
    now = overrides()
    check("restore: the file holds the snapshot's instances and meshes again, receipt back",
          set(now["instances"]) == set(kept["instances"]) and set(now["meshes"]) == set(kept["meshes"])
          and (r.get("ue") or {}).get("rev") == r.get("rev"), (sorted(now["instances"]), r.get("ue")))
    check("restore: the cleared state before it was kept too (nothing is ever lost by a restore)",
          len(state.rb.list_snapshots(OV)) >= 1)
    before_ids = set(now["instances"])
    check("attach again (a reopened window)", bpy.ops.renou.attach() == {"FINISHED"})
    B2 = state.BATCHES["test_01"]
    check("attach again: goes on from the file, not from the table", set(B2.overrides()) == before_ids,
          sorted(B2.overrides()))
    r = settle()
    check("attach again: the next publish keeps every instance (no empty overwrite)",
          set(overrides()["instances"]) == before_ids and r.get("overrides") == len(before_ids), r.get("overrides"))

    # Ash 10-10 on #37: a file that cannot be loaded back blocks publishing until the user decides
    doc = overrides()
    doc["meshes"]["PBOX_A"] = {"glb": str(out / "gone" / "PBOX_A_dead.glb"), "sha256": "0" * 64}
    OV.write_text(json.dumps(doc), encoding="utf-8")
    kept = OV.read_bytes()
    check("attach with a file that cannot be loaded back", bpy.ops.renou.attach() == {"FINISHED"})
    check("blocked: the batch is not published (not dirty, flush skips it), the file is untouched",
          "test_01" in state.BLOCKED and live.flush("test") == [] and OV.read_bytes() == kept, state.BLOCKED)
    n_snaps = len(state.rb.list_snapshots(OV, limit=200))
    check("unblock operator (start from the table)", bpy.ops.renou.unblock(batch="test_01") == {"FINISHED"})
    check("unblock only allows publishing: with the live switch off nothing goes out yet", OV.read_bytes() == kept)
    bpy.ops.renou.publish_now()
    r = settle()
    check("unblock: published from the table; the file it replaced was kept first",
          "test_01" not in state.BLOCKED and len(state.rb.list_snapshots(OV, limit=200)) == n_snaps + 1
          and state.rb.list_snapshots(OV)[0]["instances"] == len(doc["instances"]), (r.get("overrides"), state.rb.list_snapshots(OV)[:1]))
    B3 = state.BATCHES["test_01"]
    B3.group("BLD_02")[0].location.x += 7.0              # an edit that was never published
    bpy.context.view_layer.update()
    state.DIRTY.discard("test_01")
    target = state.rb.list_snapshots(OV, limit=200)[-1]["path"]
    em = next(o for o in B3.col.objects if o.type == "MESH")
    bpy.context.view_layer.objects.active = em
    em.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        refused_in_edit = bpy.ops.renou.restore_snapshot(batch="test_01", path=target) == {"CANCELLED"}
    except RuntimeError:                                 # the operator reports ERROR -> raised in background mode
        refused_in_edit = True
    bpy.ops.object.mode_set(mode="OBJECT")
    check("restore refuses in edit mode (edits there are not in the mesh, the backup would miss them)", refused_in_edit)
    check("restore operator keeps the unpublished scene first", bpy.ops.renou.restore_snapshot(batch="test_01", path=target) == {"FINISHED"})
    scene_snaps = [s for s in state.rb.list_snapshots(OV, limit=200)
                   if "scene before" in json.loads(Path(s["path"]).read_text(encoding="utf-8")).get("label", "")]
    check("restore: the scene with the unpublished edit is in archive/",
          scene_snaps and any(k for k, v in json.loads(Path(scene_snaps[0]["path"]).read_text(encoding="utf-8"))["instances"].items()
                              if B3.base.get(k, {}).get("building_id") == "BLD_02"), [s["path"] for s in scene_snaps[:1]])
    settle()

    renou_blsync.unregister()
    check("unregister cleans up", not hasattr(bpy.types.Scene, "renou_sync") and not state.BATCHES
          and live.on_depsgraph not in bpy.app.handlers.depsgraph_update_post)
except Exception:
    traceback.print_exc()
    fails.append("exception")
finally:
    mock.terminate()

print("RESULT " + ("OK" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
