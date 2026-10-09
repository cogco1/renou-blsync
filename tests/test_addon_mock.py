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
