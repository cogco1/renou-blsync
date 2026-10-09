set -uo pipefail
# #28 on the test editor: six new towers + a part swap onto a still-importing part + a second rev while importing.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/async_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:700])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(d.get('wall_s'), 's:', json.dumps(r, ensure_ascii=False)[:700])"; }
rm -f $OV $PROJ/Saved/BlSync/status_area_04_03.json
T=/workspace/shared/assets/TOWERS_150_250/glb; mkdir -p data/rt/meshes
S=$((RANDOM + 100))
for k in T150_SetbackLimestone T170_SpireBuffBrick T190_FlatRedBrick T210_WeddingCakeStone T230_SpireTerracotta T250_FlatGraniteSlab; do
  python3 perturb_glb.py $T/BLD_CBDHighTowerKit_$k.glb data/rt/meshes/P28_${k%%_*}.glb $S > /dev/null; S=$((S + 1)); done
echo "== reload (new core), level, attach, watch"
q bl_sync.py '{"action": "reload"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
b "{\"action\": \"watch\", \"overrides\": [\"$OV\"], \"interval\": 0.1}" 60
q gap_rec.py '{"mode": "start"}' 60
python3 - <<'PY'
import json, time, os, hashlib
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
J = "/workspace/jobs/look-blsync-20261009-01/"; p = J + "data/rt/async_area_04_03_overrides.json"
sha = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
ks = ["T150", "T170", "T190", "T210", "T230", "T250"]
meshes = {f"P28_{k}": {"glb": J + f"data/rt/meshes/P28_{k}.glb", "sha256": sha(J + f"data/rt/meshes/P28_{k}.glb")} for k in ks}
inst = {f"area_04_03_p28_{k}": {"part": f"P28_{k}", "era": "both", "src": "#28 test", "pos": [500 + 60 * i, -650, 0],
                                "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]} for i, k in enumerate(ks)}
inst["area_04_03_000646"] = {"pos": [25.0, 0, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}
base = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": sha(PL)}
A = dict(base, rev=1, written=time.time(), instances=inst, meshes=meshes)
open(p + ".tmp", "w").write(json.dumps(A)); os.replace(p + ".tmp", p); print("rev 1: 6 new towers + BLK_001 +25 m")
time.sleep(2.0)
B = json.loads(json.dumps(A)); B.update(rev=2, written=time.time())
B["instances"]["area_04_03_p28_T150"]["pos"] = [500, -700, 0]            # a waiting instance moves again
pl = json.load(open(PL))
sw = next(i for i in pl["instances"] if i["id"] != "area_04_03_000646")
B["instances"][sw["id"]] = {"part": "P28_T190"}                           # an existing instance swaps onto a waiting part
open(p + ".tmp", "w").write(json.dumps(B)); os.replace(p + ".tmp", p); print("rev 2 (2 s later): T150 moved again, swap", sw["id"], "-> P28_T190")
open(J + "data/rt/async_swap_id.txt", "w").write(sw["id"])
PY
R=$PROJ/Saved/BlSync/status_area_04_03.json; t0=$(date +%s.%N); seen=""
for i in $(seq 1 600); do
  line=$(python3 -c "import json; s=json.load(open('$R')); print(s.get('rev'), s.get('complete'), s.get('counts'), 'pending', s.get('pending_meshes'), 'meshes', [(m.get('part'), m.get('queued_s'), m.get('import_s'), m.get('seconds')) for m in s.get('meshes', [])], 'errors', s.get('errors'))" 2>/dev/null)
  if [ -n "$line" ] && [ "$line" != "$seen" ]; then printf "%6.1f s  %s\n" $(echo "$(date +%s.%N) - $t0" | bc) "$line" | cut -c1-600; seen="$line"; fi
  echo "$line" | grep -q "^2 True" && break; sleep 0.2; done
q gap_rec.py '{"mode": "stop"}' 60
b '{"action": "status"}' 30
b '{"action": "where", "name": "A0403", "inst": "area_04_03_p28_T150"}' 30
b "{\"action\": \"materials\", \"name\": \"A0403\", \"inst\": [\"$(cat data/rt/async_swap_id.txt)\", \"area_04_03_p28_T250\"]}" 30
b '{"action": "where", "name": "A0403", "inst": "area_04_03_000646"}' 30
grep "BLSYNC\] meshes in\|BLSYNC\] applied async" $J/logs/ue.log | tail -8 | cut -c1-260
b '{"action": "detach"}' 120
