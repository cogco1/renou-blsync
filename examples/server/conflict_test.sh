set -uo pipefail
J=/workspace/jobs/look-blsync-20261009-01; cd $J
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/test/area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:900])"; }
q bl_sync.py '{"action": "reload"}' 60
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
q bl_sync.py "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 300
q bl_conflict_props.py '{}' 60
python3 - <<'PY'
import json, time, os, hashlib
PL="/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
p="/workspace/jobs/look-blsync-20261009-01/data/test/area_04_03_overrides.json"
ov={"schema":"renou-overrides/1","batch":"area_04_03","base_sha256":hashlib.sha256(open(PL,"rb").read()).hexdigest(),"rev":int(time.time()),"written":time.time(),
    "instances":{"area_04_03_000646":{"pos":[60.0,0.0,0.0],"quat_wxyz":[1,0,0,0],"scale":[1,1,1]}}, "meshes":{}}
open(p+".tmp","w").write(json.dumps(ov)); os.replace(p+".tmp",p); print("override: BLK_001 +60 m")
PY
q bl_sync.py "{\"action\": \"apply\", \"overrides\": \"$OV\"}" 120
python3 - <<'PY'
import json, time, os
p="/workspace/jobs/look-blsync-20261009-01/data/test/area_04_03_overrides.json"
ov=json.load(open(p)); ov.update(rev=ov["rev"]+1, written=time.time(), instances={})
open(p+".tmp","w").write(json.dumps(ov)); os.replace(p+".tmp",p)
PY
q bl_sync.py "{\"action\": \"apply\", \"overrides\": \"$OV\"}" 120
q bl_conflict_props.py '{"remove": true}' 60
q bl_sync.py '{"action": "detach"}' 120
