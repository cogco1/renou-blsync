set -uo pipefail
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/reentry_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:300])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:300])"; }
rm -f $OV
q bl_sync.py '{"action": "reload"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
b "{\"action\": \"watch\", \"overrides\": [\"$OV\"], \"interval\": 0.1}" 60
cp /workspace/shared/assets/TOWERS_150_250/glb/BLD_CBDHighTowerKit_T250_FlatGraniteSlab.glb $J/data/rt/meshes/RE_T250.glb
python3 - <<'PY'
import json, time, os, hashlib
PL="/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
J="/workspace/jobs/look-blsync-20261009-01/"; p=J+"data/rt/reentry_area_04_03_overrides.json"; g=J+"data/rt/meshes/RE_T250.glb"
sha=lambda f: hashlib.sha256(open(f,"rb").read()).hexdigest()
base={"schema":"renou-overrides/1","batch":"area_04_03","base_sha256":sha(PL)}
A=dict(base, rev=1, written=time.time(), instances={"area_04_03_reobj":{"part":"RE_T250","era":"both","src":"re-entry test","pos":[600,-600,0],"quat_wxyz":[1,0,0,0],"scale":[1,1,1]}},
       meshes={"RE_T250":{"glb":g,"sha256":sha(g)}})
open(p+".tmp","w").write(json.dumps(A)); os.replace(p+".tmp",p); print("rev 1 written (needs an import)")
time.sleep(1.0)
B=dict(A, rev=2, written=time.time())
B["instances"]=dict(A["instances"], area_04_03_000646={"pos":[25.0,0,0],"quat_wxyz":[1,0,0,0],"scale":[1,1,1]})
open(p+".tmp","w").write(json.dumps(B)); os.replace(p+".tmp",p); print("rev 2 written 1 s later (one more move)")
PY
for i in $(seq 1 60); do python3 -c "import json,sys; s=json.load(open('$PROJ/Saved/BlSync/status_area_04_03.json')); sys.exit(0 if s.get('rev')==2 else 1)" 2>/dev/null && break; sleep 1; done
python3 -c "import json; s=json.load(open('$PROJ/Saved/BlSync/status_area_04_03.json')); print('final receipt rev', s.get('rev'), s.get('counts'), 'overrides', s.get('overrides'), 'errors', s.get('errors'))"
grep "BLSYNC\] applied reentry" $J/logs/ue.log | tail -3 | cut -c1-160
b '{"action": "where", "name": "A0403", "inst": "area_04_03_000646"}' 60
b '{"action": "status"}' 30
b '{"action": "detach"}' 60
