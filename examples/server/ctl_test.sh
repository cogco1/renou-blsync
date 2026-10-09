set -uo pipefail
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/ctl_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print('lk_session:', json.dumps(r, ensure_ascii=False)[:300])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print('own channel', d.get('wall_s'), 's:', json.dumps(r, ensure_ascii=False)[:400])"; }
rm -f $PROJ/Saved/BlSync/session.json
python3 - <<'PY'
import json, time, os, hashlib
PL="/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
p="/workspace/jobs/look-blsync-20261009-01/data/rt/ctl_area_04_03_overrides.json"
ov={"schema":"renou-overrides/1","batch":"area_04_03","base_sha256":hashlib.sha256(open(PL,"rb").read()).hexdigest(),"rev":1,"written":time.time(),
    "instances":{"area_04_03_000646":{"pos":[33.0,0.0,0.0],"quat_wxyz":[1,0,0,0],"scale":[1,1,1]}}}
open(p+".tmp","w").write(json.dumps(ov)); os.replace(p+".tmp",p); print("override: BLK_001 +33 m")
PY
echo "== 1. bootstrap through lk_session (loads the core, starts its own channel)"
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
q bl_sync.py '{"action": "status"}' 60
echo "== 2. everything else through the own channel"
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
b "{\"action\": \"watch\", \"overrides\": [\"$OV\"], \"interval\": 0.1}" 60
sleep 1
b '{"action": "where", "name": "A0403", "inst": "area_04_03_000646"}' 60
b '{"action": "status"}' 60
echo "== 3. editor restart"
q quit '{}' 60
for i in $(seq 1 40); do [ -f /workspace/jobs/look-blsync-20261009-12/.run/exit_code ] && break; sleep 2; done
mkdir /workspace/jobs/look-blsync-20261009-13
tmux new-session -d -s blsync-editor3 "NULLRHI=1 MAXMIN=180 GPU_LANE=cpu bash /workspace/tools/run-gpu-job.sh /workspace/jobs/look-blsync-20261009-13 bash $J/session.sh"
now=$(date +%s); for i in $(seq 1 60); do python3 -c "import json,sys; sys.exit(0 if json.load(open('$PROJ/Saved/LookDevCtrl/ready.json'))['t']>$now else 1)" 2>/dev/null && break; sleep 3; done
echo "== 4. one restore through lk_session brings everything back"
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
q bl_sync.py '{"action": "restore"}' 300
sleep 1
b '{"action": "where", "name": "A0403", "inst": "area_04_03_000646"}' 60
echo "== 5. detach through the own channel clears the session"
b '{"action": "detach"}' 120
python3 -c "import json; print('session after detach:', json.load(open('$PROJ/Saved/BlSync/session.json')))"
