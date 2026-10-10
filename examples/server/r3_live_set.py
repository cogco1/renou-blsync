import json, sys
sys.path.insert(0, "/workspace/jobs/look-blsync-20261009-01/lib")
import renou_blsync_lib as rb
R = "/workspace/shared/eng-inst/u20b_r1/area_04_03/"
B = rb.Batch(R + "area_04_03_placements.json", out="/workspace/jobs/look-blsync-20261009-01/data/area_04_03_overrides.json",
             parts_glb=R + "area_04_03_parts.glb", load_meshes=False)
B.move(B.group("V10_CBDFILL_BLK_001"), (60.0, 0.0, 0.0))
B.rotate(B.group("V10_CBDFILL_BLK_002"), 15.0)
r = B.publish("R3 live test: preview state on during the VFX save")
print("R3SET " + json.dumps({k: (r["ue"] or {}).get(k) for k in ("rev", "counts", "save_guard", "latency_s", "errors")}))
