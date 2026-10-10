"""Blender→UE 实时预览 #18 test: take one ground tile <tile>_LOD0 out of a ground_core glTF file, lift it 5 m (a stand-in
for a real terrain edit) and export only that tile as a one-mesh GLB, the way the Blender side (#5) will.
  blender -b --factory-startup --python tile_edit.py -- <terrain.gltf> <tile id> <out.glb>"""
import hashlib, json, sys
import bpy
from mathutils import Matrix

src, tid, out = sys.argv[sys.argv.index("--") + 1:][:3]
bpy.ops.import_scene.gltf(filepath=src)
obj = bpy.data.objects.get(tid + "_LOD0")
assert obj is not None and obj.type == "MESH", f"no {tid}_LOD0"
mw = obj.matrix_world.copy()
me = obj.data.copy()
me.transform(mw)                                   # bake the node transform: the GLB node is identity, world coordinates
me.transform(Matrix.Translation((0, 0, 5.0)))
new = bpy.data.objects.new(tid + "_LOD0", me)
bpy.context.scene.collection.objects.link(new)
for o in bpy.context.view_layer.objects:
    o.select_set(False)
new.select_set(True)
bpy.context.view_layer.objects.active = new
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_apply=False, export_yup=True,
                          export_animations=False, export_cameras=False, export_lights=False)
print("TILEEDIT " + json.dumps({"tile": tid, "slots": [m.name for m in me.materials if m], "verts": len(me.vertices),
                                "sha256": hashlib.sha256(open(out, "rb").read()).hexdigest()}))
