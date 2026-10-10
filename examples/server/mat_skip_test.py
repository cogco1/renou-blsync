import json, sys
sys.path.insert(0, "/workspace/jobs/look-blsync-20261009-01/lib")
import bpy
from mathutils import Matrix
import renou_blsync_lib as rb
R = "/workspace/shared/eng-inst/u20b_r1/area_04_03/"
J = "/workspace/jobs/look-blsync-20261009-01/"
B = rb.Batch(R + "area_04_03_placements.json", out=J + "data/test/area_04_03_overrides.json", parts_glb=R + "area_04_03_parts.glb",
             status=J + "BlSyncTest/Saved/BlSync/status.json")
out = {}
p2 = B.group("V10_CBDFILL_BLK_002")[0]["blsync_part"]
B.meshes[p2].transform(Matrix.Diagonal((1.0, 1.0, 1.07, 1.0)))
B.export_part(p2)
u = B.publish("reimport known part").get("ue") or {}
out["reimport"] = [{k: m.get(k) for k in ("part", "glb_materials", "seconds")} | {"hows": sorted({v[1] for v in (m.get("slots") or {}).values()})} for m in u.get("meshes") or []]
me = B.new_part(p2, "PBLKEEP0002")
me.materials[0] = bpy.data.materials.new("BLSYNC_TEST_NEWSLOT3")
me.materials[1] = bpy.data.materials.new("02 | pale cast edges")
B.export_part("PBLKEEP0002")
B.set_part(B.group("V10_CBDFILL_BLK_004"), "PBLKEEP0002")
u = B.publish("new part with a KEEP slot").get("ue") or {}
out["newpart_keep"] = [{k: m.get(k) for k in ("part", "glb_materials", "seconds")} for m in u.get("meshes") or []]
out["unmapped"] = u.get("unmapped_slots"); out["errors"] = u.get("errors")
B.reset(); B.publish("reset")
print("MATSKIP " + json.dumps(out, ensure_ascii=False))
