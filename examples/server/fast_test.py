import json, sys, time
sys.path.insert(0, "/workspace/jobs/look-blsync-20261009-01/lib")
import renou_blsync_lib as rb
R = "/workspace/shared/eng-inst/u20b_r1/area_04_03/"
J = "/workspace/jobs/look-blsync-20261009-01/"
t0 = time.time()
B = rb.Batch(R + "area_04_03_placements.json", out=J + "data/area_04_03_overrides.json", parts_glb=R + "area_04_03_parts.glb",
             load_meshes=False, status=J + "BlSyncTest/Saved/BlSync/status.json")
res = {"load_s": round(time.time() - t0, 2), "parts_with_bounds": len(B.bounds)}
blk = B.group("V10_CBDFILL_BLK_001")
res["centre_glb_header"] = [round(v, 3) for v in B.centre(blk, base=False)]
hub = B.group("V10_TWR_000_BLD_HubTower_C1Empire")
res["hub_centre"] = [round(v, 3) for v in B.centre(hub)]
B.rotate(blk, 15.0)
r = B.publish("fast mode: BLK_001 15 deg in place")
res["publish"] = {"rev": r["rev"], "ue_latency": (r["ue"] or {}).get("latency_s"), "counts": (r["ue"] or {}).get("counts")}
res["total_s"] = round(time.time() - t0, 2)
print("FAST " + json.dumps(res))
