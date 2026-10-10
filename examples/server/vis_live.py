"""人偶之心 · Blender→UE 实时预览 2026-10-09: acceptance in 视效's live editor (L_S02, present era, P1): move one CBD block,
swap one, re-import one part's mesh, reset - a P1 still and the material paths of the touched instances after each step.
  blender -b --factory-startup --python vis_live.py
Uses the same function library engineering uses (renou_blsync_lib)."""
import json, os, subprocess, sys, time
sys.path.insert(0, "/workspace/jobs/look-blsync-20261009-01/lib")
import renou_blsync_lib as rb
from mathutils import Matrix

R = "/workspace/shared/eng-inst/u20b_r1/area_04_03/"
J = "/workspace/jobs/look-blsync-20261009-01/"
G = "/workspace/guest/look-ue-20261008/"
ENV = dict(os.environ, PROJ=G + "HarborLookMS")


def live(script, req, timeout=300):
    r = subprocess.run(["python3", G + "live/live_req.py", script, json.dumps(req), str(timeout)], env=ENV,
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"raw": r.stdout[-300:], "err": r.stderr[-300:]}


CAM = os.environ.get("BLSYNC_CAM", "P1_ssw205")
PFX = os.environ.get("BLSYNC_PFX", "live")


def shot(tag):
    r = live("lk_shot.py", {"cam": CAM, "res": [1600, 900], "out": f"{G}tmp/blsync_check/{PFX}_{tag}.png", "frames": 45}, 300)
    return (r.get("done") or {}).get("status")


B = rb.Batch(R + "area_04_03_placements.json", out=J + "data/area_04_03_overrides.json", parts_glb=R + "area_04_03_parts.glb",
             load_meshes=True)
blk1, blk2, blk4 = (B.group(f"V10_CBDFILL_BLK_00{k}") for k in (1, 2, 4))
ids = [blk1[0]["blsync_id"], blk2[0]["blsync_id"], blk4[0]["blsync_id"]]
p2 = blk2[0]["blsync_part"]
res = {"ids": ids, "steps": []}


def step(tag, label):
    r = B.publish(label)
    u = r["ue"] or {}
    m = live("bl_sync.py", {"action": "materials", "name": "area_04_03", "inst": ids}, 60).get("report")
    res["steps"].append({"tag": tag, "label": label, "rev": r["rev"], "latency_s": u.get("latency_s"), "ue_s": u.get("seconds"),
                         "counts": u.get("counts"), "errors": u.get("errors"), "meshes": u.get("meshes"),
                         "save_guard": u.get("save_guard"), "shot": shot(tag), "materials": m})


res["base_shot"] = shot("0_base")
res["base_materials"] = live("bl_sync.py", {"action": "materials", "name": "area_04_03", "inst": ids}, 60).get("report")
B.move(blk1, (60.0, 0.0, 0.0))
step("1_move", "BLK_001 60 m east")
c2, c4 = B.centre(blk2), B.centre(blk4)
B.set_part(blk4, p2)
B.move(blk4, (c4.x - c2.x, c4.y - c2.y, 0.0))         # BLK_002's mesh standing where BLK_004 was
step("2_swap", "BLK_004 shows BLK_002's part, at BLK_004's place")
B.meshes[p2].transform(Matrix.Diagonal((1.0, 1.0, 1.25, 1.0)))
B.export_part(p2)
step("3_mesh", "BLK_002's part 25 % taller (single-part re-import)")
B.reset()
step("4_reset", "reset: back to the release table")
Path = __import__("pathlib").Path
Path(J + f"out/vis_{PFX}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print("VISLIVE " + json.dumps([{k: s[k] for k in ("tag", "latency_s", "ue_s", "counts", "errors", "shot")} for s in res["steps"]]))
