# SPDX-License-Identifier: GPL-3.0-or-later
"""人偶之心 · Blender→UE 实时预览 2026-10-09: "改了的网格单独重导" test, Blender side (headless).
  blender -b --factory-startup --python bl_mesh_test.py -- --parts P_parts.glb --placements P.json --part <part>
        --scale-z 1.3 --meshdir <dir> --out O_overrides.json --status S.json
Imports the batch's parts GLB once, edits ONE part's mesh data (scales it in Z: a taller tower), exports only that part as
<meshdir>/<part>_<sha8>.glb (object and mesh named exactly <part>, identity transform, glTF Y-up like the release), adds it
to the cumulative override file and waits for UE to report the rev. Prints the timings."""
import argparse, hashlib, json, os, sys, time
from pathlib import Path
import bpy
from mathutils import Matrix

ap = argparse.ArgumentParser()
for k in ("--parts", "--placements", "--part", "--meshdir", "--out", "--status"):
    ap.add_argument(k, required=True)
ap.add_argument("--scale-z", type=float, default=1.3)
ap.add_argument("--timeout", type=float, default=300)
a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
T = {}
t = time.time()
bpy.ops.import_scene.gltf(filepath=a.parts)
T["import_parts_glb_s"] = round(time.time() - t, 1)
obj = bpy.data.objects.get(a.part)
assert obj is not None and obj.type == "MESH", f"no mesh object {a.part}"
T["part_triangles_before"] = sum(len(p.vertices) - 2 for p in obj.data.polygons)

# the edit a modeller would make: here a 30 % taller block (mesh data, not the object transform)
t = time.time()
orig = obj.data
orig.name = a.part + "_orig"                           # free the name: the exported mesh must be called exactly <part>
me = orig.copy()                                       # never touch other objects that might share the mesh
me.transform(Matrix.Diagonal((1.0, 1.0, a.scale_z, 1.0)))
me.name = a.part
obj.data = me
obj.matrix_world = Matrix.Identity(4)
for o in bpy.context.view_layer.objects:
    o.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
Path(a.meshdir).mkdir(parents=True, exist_ok=True)
tmp = Path(a.meshdir) / f"{a.part}.tmp.glb"
bpy.ops.export_scene.gltf(filepath=str(tmp), export_format="GLB", use_selection=True, export_apply=False,
                          export_yup=True, export_animations=False, export_cameras=False, export_lights=False)
sha = hashlib.sha256(tmp.read_bytes()).hexdigest()
glb = Path(a.meshdir) / f"{a.part}_{sha[:8]}.glb"
os.replace(tmp, glb)
T["export_one_part_s"] = round(time.time() - t, 2)
T["glb_bytes"] = glb.stat().st_size

PL = Path(a.placements)
out = Path(a.out)
ov = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {
    "schema": "renou-overrides/1", "batch": json.loads(PL.read_text(encoding="utf-8-sig"))["batch"],
    "base_sha256": hashlib.sha256(PL.read_bytes()).hexdigest(), "rev": 0, "instances": {}}
ov["rev"] = int(ov.get("rev") or 0) + 1 if isinstance(ov.get("rev"), int) else 1000
ov["meshes"] = dict(ov.get("meshes") or {}, **{a.part: {"glb": str(glb), "sha256": sha}})
ov["label"] = f"mesh {a.part} z x{a.scale_z}"
ov["written"] = time.time()
tmpj = out.with_suffix(".tmp")
tmpj.write_text(json.dumps(ov, ensure_ascii=False), encoding="utf-8")
os.replace(tmpj, out)
while time.time() - ov["written"] < a.timeout:
    try:
        st = json.loads(Path(a.status).read_text(encoding="utf-8"))
    except Exception:
        st = {}
    if st.get("rev") == ov["rev"] or st.get("error"):
        T["ue"] = st
        T["end_to_end_s"] = round(st.get("applied_at", time.time()) - ov["written"] + T["export_one_part_s"], 2)
        break
    time.sleep(0.05)
print("BLSYNC_MESH " + json.dumps(T, ensure_ascii=False))
