"""LS01 add-on (blender/renou_blsync, GitHub main) end to end against the REAL UE test editor (-nullrhi), batch
area_01_04 (1,825 instances), override file of its own so nobody else's preview is touched.
  blender -b --factory-startup --python-exit-code 1 --python addon_ue_test.py
Background Blender has no event loop: the timer callback (live.tick) is called by hand, as in tests/test_addon_mock.py."""
import json, sys, time, traceback
from pathlib import Path
sys.path.insert(0, "/workspace/jobs/look-blsync-20261009-01/addon")
import bpy
import renou_blsync
from renou_blsync import live, state

R = Path("/workspace/shared/eng-inst/u20b_r1/area_01_04")
J = Path("/workspace/jobs/look-blsync-20261009-01")
OV = J / "data/rt/area_01_04_overrides.json"
ST = J / "BlSyncTest/Saved/BlSync/status.json"
fails, T = [], {}


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {info}" if info != "" else ""))
    if not cond:
        fails.append(name)


def settle(timeout=20.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        live.tick()
        if not state.DIRTY and live.WORKER is not None and live.WORKER.idle():
            live.collect_results()
            r = state.RESULTS.get("area_01_04") or {}
            if r.get("ue"):
                r["e2e_s"] = round(time.time() - t0, 2)
                return r
        time.sleep(0.05)
    return state.RESULTS.get("area_01_04") or {}


def counts(r):
    return (r.get("ue") or {}).get("counts") or {}


try:
    renou_blsync.register()
    s = bpy.context.scene.renou_sync
    s.placements, s.parts_glb = str(R / "area_01_04_placements.json"), str(R / "area_01_04_parts.glb")
    s.out, s.status, s.writeback_dir = str(OV), str(ST), str(J / "out/addon_writeback")
    t = time.time()
    check("attach operator", bpy.ops.renou.attach() == {"FINISHED"})
    T["attach_s"] = round(time.time() - t, 1)
    B = state.BATCHES["area_01_04"]
    keys = [k for k, n in B.srcs("") if n >= 1]
    s.live = True
    r = settle()
    check("live on: first publish, UE receipt", bool(r.get("ue")) and not (r.get("ue") or {}).get("errors"), r.get("ue"))

    g = B.group(keys[0])
    for o in g:
        o.location.x += 20.0                        # a hand / script edit; nothing calls publish
    bpy.context.view_layer.update()
    r = settle()
    T["move_e2e_s"] = r.get("e2e_s")
    check("move goes out by itself", counts(r).get("moved") == len(g), (counts(r), len(g)))

    src = B.group(keys[1])[0]
    dup = src.copy()                                # what Shift+D does
    B.col.objects.link(dup)
    dup.location.y += 40.0
    bpy.context.view_layer.update()
    r = settle()
    check("Shift+D copy -> UE added 1", counts(r).get("added") == 1, counts(r))

    gone = B.group(keys[2])[0]
    bpy.data.objects.remove(gone, do_unlink=True)
    bpy.context.view_layer.update()
    r = settle()
    check("delete -> UE hidden 1", counts(r).get("hidden") == 1, counts(r))

    me = B.group(keys[3])[0].data
    for v in me.vertices:
        v.co.z *= 1.2
    me.update()
    bpy.context.view_layer.update()
    r = settle(60)
    m = (r.get("ue") or {}).get("meshes") or []
    T["mesh_e2e_s"] = r.get("e2e_s")
    check("mesh edit -> one part re-imported in UE", len(m) == 1 and not (r.get("ue") or {}).get("errors"), m)

    check("write-back operator", bpy.ops.renou.write_back() == {"FINISHED"})
    s.live = False
    check("live off", not state.LIVE)
    check("reset operator", bpy.ops.renou.reset() == {"FINISHED"})
    s.live = True
    r = settle()
    check("after reset: no overrides, UE back to the table", r.get("overrides") == 0 and not (r.get("ue") or {}).get("errors"),
          (r.get("overrides"), counts(r)))
    s.live = False
except Exception:
    traceback.print_exc()
    fails.append("exception")
print("ADDONUE " + json.dumps({"fails": fails, "timing": T}))
sys.exit(1 if fails else 0)
