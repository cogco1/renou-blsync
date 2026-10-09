# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender→UE 实时预览: engineering-style scripted test of renou_blsync_lib against the UE test editor (headless)."""
import json, sys, time
sys.path.insert(0, "/workspace/jobs/look-blsync-20261009-01/lib")
import renou_blsync_lib as rb
R = "/workspace/shared/eng-inst/u20b_r1/area_04_03/"
J = "/workspace/jobs/look-blsync-20261009-01/"
t = time.time()
B = rb.Batch(R + "area_04_03_placements.json", out=J + "data/area_04_03_overrides.json", parts_glb=R + "area_04_03_parts.glb")
res = {"load_s": round(time.time() - t, 1), "cbd_keys": len(B.srcs("CBDFILL")), "hub": B.srcs("HubTower")}
blk = B.group("V10_CBDFILL_BLK_001")
c0 = B.centre(blk, base=False)
B.rotate(blk, 15.0)                                   # about its own footprint centre
c1 = B.centre(blk, base=False)
res["blender_centre_before_after"] = [[round(v, 3) for v in c0], [round(v, 3) for v in c1]]
res["step1_rotate"] = B.publish("rotate BLK_001 15 deg in place")
# mesh edit of the part BLK_002 uses, exported alone
p2 = B.base[B.group("V10_CBDFILL_BLK_002")[0]["blsync_id"]]["part"]
from mathutils import Matrix
B.meshes[p2].transform(Matrix.Diagonal((1.0, 1.0, 1.1, 1.0)))
res["export"] = B.export_part(p2)
res["step2_mesh"] = B.publish("BLK_002 part 10 % taller")
# a brand-new part for BLK_003 (copy of BLK_002's part)
b3 = B.group("V10_CBDFILL_BLK_004")
B.new_part(p2, "PBLTEST0001")
B.set_part(b3, "PBLTEST0001")
B.export_part("PBLTEST0001")
res["step3_newpart"] = B.publish("BLK_004 -> new part PBLTEST0001")
res["ids"] = {"blk1": blk[0]["blsync_id"], "blk2": B.group("V10_CBDFILL_BLK_002")[0]["blsync_id"], "blk4": b3[0]["blsync_id"], "p2": p2}
res["write_back"] = B.write_back(J + "out/write_back_test")
# reset is done from UE after the probes

print("LIBTEST " + json.dumps(res, ensure_ascii=False, default=str))
