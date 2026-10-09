import json, sys
sys.path.insert(0, "/workspace/jobs/look-blsync-20261009-01/lib")
import bpy
import renou_blsync_lib as rb
R = "/workspace/shared/eng-inst/u20b_r1/area_04_03/"
J = "/workspace/jobs/look-blsync-20261009-01/"
B = rb.Batch(R + "area_04_03_placements.json", out=J + "data/test/area_04_03_overrides.json", parts_glb=R + "area_04_03_parts.glb",
             status=J + "BlSyncTest/Saved/BlSync/status.json")
p2 = B.group("V10_CBDFILL_BLK_002")[0]["blsync_part"]
me = B.new_part(p2, "PBLSLOT0001")
m_new = bpy.data.materials.new("BLSYNC_TEST_NEWSLOT")          # in no table, in no batch -> placeholder
m_keep = bpy.data.materials.new("01 | warm pale naval paint")  # table says KEEP_GLB -> import's own material
me.materials[0] = m_new
me.materials[1] = m_keep
B.export_part("PBLSLOT0001")
B.set_part(B.group("V10_CBDFILL_BLK_004"), "PBLSLOT0001")
r = B.publish("slot rule test")
u = r["ue"] or {}
print("SLOTTEST " + json.dumps({"counts": u.get("counts"), "errors": u.get("errors"), "unmapped": u.get("unmapped_slots"),
                                 "meshes": u.get("meshes")}, ensure_ascii=False))
