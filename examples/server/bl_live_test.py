"""人偶之心 · Blender→UE 实时预览 2026-10-09: Blender side of the closed-loop test (headless reference implementation of
the override writer; the interactive add-on is specified in SPEC_Blender侧插件.md).
  blender -b --factory-startup --python bl_live_test.py -- --placements P.json --out O_overrides.json --status S.json
Loads the batch as one Empty per instance (custom props blsync_id / blsync_part / blsync_era / blsync_src), then runs the
scripted edits below like a user would (bpy transforms only), and after each edit diffs every object's matrix_world
against the base table and writes the cumulative override file atomically. Waits for the UE status file to report the same
rev and records the latency. Writes <out>.results.json."""
import argparse, hashlib, json, math, os, sys, time
from pathlib import Path
import bpy
from mathutils import Matrix, Quaternion, Vector

ap = argparse.ArgumentParser()
ap.add_argument("--placements", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--status", required=True)
ap.add_argument("--timeout", type=float, default=60)
ap.add_argument("--drag", type=int, default=20)
a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
PL, OUT, STATUS = Path(a.placements), Path(a.out), Path(a.status)
base_sha = hashlib.sha256(PL.read_bytes()).hexdigest()
data = json.loads(PL.read_text(encoding="utf-8-sig"))
BASE = {i["id"]: i for i in data["instances"]}


def mat_of(rec):
    q = Quaternion(rec.get("quat_wxyz") or Quaternion((0, 0, 1), math.radians(rec.get("yaw_deg", 0.0))))
    s = rec.get("scale", 1.0)
    s = Vector(s) if isinstance(s, list) else Vector((s, s, s))
    return Matrix.LocRotScale(Vector(rec["pos"]), q, s)


# 1. load: one Empty per instance (the add-on uses linked duplicates of the part meshes instead; the diff is the same)
t = time.time()
col = bpy.data.collections.new("BLSYNC|" + data["batch"])
bpy.context.scene.collection.children.link(col)
OBJ = {}
for iid, rec in BASE.items():
    o = bpy.data.objects.new(iid, None)
    o["blsync_id"], o["blsync_part"], o["blsync_era"], o["blsync_src"] = iid, rec["part"], rec.get("era", "both"), rec.get("src", "")
    o.matrix_world = mat_of(rec)
    col.objects.link(o)
    OBJ[iid] = o
bpy.context.view_layer.update()
load_s = time.time() - t


def diff_state(o, rec):
    """override entry for object o, or None when it matches its base record."""
    loc, q, s = o.matrix_world.decompose()
    if q.w < 0:
        q.negate()
    entry = {"pos": [round(v, 5) for v in loc], "quat_wxyz": [round(v, 7) for v in q], "scale": [round(v, 6) for v in s]}
    if o.get("blsync_deleted"):
        return {"deleted": True}
    if rec is None:
        return dict(entry, part=o["blsync_part"], era=o["blsync_era"], src=o["blsync_src"])
    bl, bq, bs = mat_of(rec).decompose()
    moved = (loc - bl).length > 1e-4 or bq.rotation_difference(q).angle > 1e-5 or (s - bs).length > 1e-5
    swapped = o["blsync_part"] != rec["part"]
    if not moved and not swapped:
        return None
    if swapped:
        entry["part"] = o["blsync_part"]
    return entry


REV = {"n": 0}


def publish(label):
    t0 = time.time()
    inst = {}
    for o in col.objects:
        iid = o.get("blsync_id")
        if not iid:
            continue
        e = diff_state(o, BASE.get(iid))
        if e:
            inst[iid] = e
    REV["n"] += 1
    ov = {"schema": "renou-overrides/1", "batch": data["batch"], "base_sha256": base_sha, "rev": REV["n"],
          "label": label, "written": time.time(), "instances": inst}
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(ov, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, OUT)
    diff_s = ov["written"] - t0
    # wait for UE
    while time.time() - ov["written"] < a.timeout:
        try:
            st = json.loads(STATUS.read_text(encoding="utf-8"))
        except Exception:
            st = {}
        if st.get("rev") == REV["n"]:
            return {"rev": REV["n"], "label": label, "overrides": len(inst), "blender_diff_s": round(diff_s, 3),
                    "ue_apply_s": st.get("seconds"), "end_to_end_s": round(st["applied_at"] - ov["written"] + diff_s, 3),
                    "counts": st.get("counts"), "errors": st.get("errors")}
        if st.get("error"):
            return {"rev": REV["n"], "label": label, "error": st["error"][-400:]}
        time.sleep(0.02)
    return {"rev": REV["n"], "label": label, "error": "timeout"}


def group(src_prefix):
    return [o for o in col.objects if str(o.get("blsync_src", "")).split(" | ")[0] == src_prefix]


def centroid(objs):
    return sum((o.matrix_world.translation for o in objs), Vector()) / len(objs)


results = {"load_s": round(load_s, 2), "instances": len(OBJ), "steps": []}
R = results["steps"].append
cbd1 = group("V10_CBDFILL_BLK_001")[0]
cbd2 = group("V10_CBDFILL_BLK_002")[0]
narrow = group("AP_E_NARROW_432")

# step 1: move one CBD block 40 m east (the near-term need: shift CBD towers)
cbd1.matrix_world = Matrix.Translation((40.0, 0.0, 0.0)) @ cbd1.matrix_world
R(publish("move CBD_BLK_001 +40 m x"))
# step 2: a 20-part building group: rotate 15 deg about its centroid and lift 5 m
c = centroid(narrow)
M = Matrix.Translation(c + Vector((0, 0, 5.0))) @ Matrix.Rotation(math.radians(15), 4, "Z") @ Matrix.Translation(-c)
for o in narrow:
    o.matrix_world = M @ o.matrix_world
R(publish("rotate AP_E_NARROW_432 (20 parts) 15 deg + lift 5 m"))
# step 3: swap the mesh of CBD block 001 for block 002's part (換一个件)
cbd1["blsync_part"] = cbd2["blsync_part"]
R(publish("swap CBD_BLK_001 part -> BLK_002 part"))
# step 4: a copy (new id) of block 002, 60 m north
cp = cbd2.copy()
cp["blsync_id"] = data["batch"] + "_bl000001"
cp.matrix_world = Matrix.Translation((0.0, 60.0, 0.0)) @ cbd2.matrix_world
col.objects.link(cp)
R(publish("copy CBD_BLK_002 as new id +60 m y"))
# step 5: delete one part of the narrow group
narrow[0]["blsync_deleted"] = True
R(publish("delete one part of AP_E_NARROW_432"))
# step 6: drag CBD block 002 like a mouse drag: N small moves, one publish each
lat = []
for k in range(a.drag):
    cbd2.matrix_world = Matrix.Translation((2.0, 0.0, 0.0)) @ cbd2.matrix_world
    r = publish(f"drag {k}")
    lat.append(r.get("end_to_end_s"))
results["drag"] = {"n": a.drag, "end_to_end_s": lat, "max_s": max(x for x in lat if x is not None) if any(lat) else None}
# step 7: undo everything (back to the table): restore base matrices and parts, drop the copy and the delete flag
bpy.data.objects.remove(cp)
for iid, o in OBJ.items():
    o.matrix_world = mat_of(BASE[iid])
    o["blsync_part"] = BASE[iid]["part"]
    if "blsync_deleted" in o:
        del o["blsync_deleted"]
R(publish("revert all"))
Path(str(OUT) + ".results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
print("BLSYNC_RESULTS " + json.dumps(results, ensure_ascii=False))
