set -uo pipefail
J=/workspace/jobs/look-blsync-20261009-01; cd $J
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/test/area_04_03_overrides.json
mkdir -p $J/data/test/meshes
cp /workspace/shared/assets/TOWERS_150_250/glb/BLD_CBDHighTowerKit_T210_WeddingCakeStone.glb $J/data/test/meshes/OBJ_T210.glb
cp /workspace/shared/assets/MESHY_normalized/glb/MESHY_M07_IndustrialHQClockTower.glb $J/data/test/meshes/OBJ_M07.glb
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:1500])"; }
q bl_sync.py '{"action": "reload"}' 60
q bl_sync.py "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 300
python3 - <<'PY'
import json, time, os, hashlib
PL="/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
M="/workspace/jobs/look-blsync-20261009-01/data/test/meshes/"
sha=lambda f: hashlib.sha256(open(f,"rb").read()).hexdigest()
ov={"schema":"renou-overrides/1","batch":"area_04_03","base_sha256":sha(PL),"rev":int(time.time()),"written":time.time(),
    "instances":{"area_04_03_obj_T210_01":{"part":"OBJ_T210","era":"both","src":"OBJ BLD_CBDHighTowerKit T210","pos":[650,-500,0],"quat_wxyz":[1,0,0,0],"scale":[1,1,1]},
                 "area_04_03_obj_M07_01":{"part":"OBJ_M07","era":"both","src":"OBJ MESHY_M07 clock tower","pos":[720,-450,0],"quat_wxyz":[1,0,0,0],"scale":[1,1,1]}},
    "meshes":{"OBJ_T210":{"glb":M+"OBJ_T210.glb","sha256":sha(M+"OBJ_T210.glb")},"OBJ_M07":{"glb":M+"OBJ_M07.glb","sha256":sha(M+"OBJ_M07.glb")}}}
p="/workspace/jobs/look-blsync-20261009-01/data/test/area_04_03_overrides.json"
open(p+".tmp","w").write(json.dumps(ov)); os.replace(p+".tmp",p); print("override: two new objects")
PY
q bl_sync.py "{\"action\": \"apply\", \"overrides\": \"$OV\"}" 600
q bl_sync.py '{"action": "materials", "name": "A0403", "inst": ["area_04_03_obj_T210_01", "area_04_03_obj_M07_01"]}' 60
python3 - <<'PY'
import json, time, os
p="/workspace/jobs/look-blsync-20261009-01/data/test/area_04_03_overrides.json"
ov=json.load(open(p)); ov.update(rev=ov["rev"]+1, written=time.time(), instances={}, meshes={})
open(p+".tmp","w").write(json.dumps(ov)); os.replace(p+".tmp",p)
PY
q bl_sync.py "{\"action\": \"apply\", \"overrides\": \"$OV\"}" 120
q bl_sync.py '{"action": "detach"}' 120
