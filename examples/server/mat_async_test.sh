set -uo pipefail
# #28 with GLB materials: the 4 CBD towers whose slots keep the GLB material (KEEP_GLB in 视效's table) imported
# asynchronously as new parts on the test editor; editor tick gaps and the slot materials afterwards.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/matasync_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:900])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(d.get('wall_s'), 's:', json.dumps(r, ensure_ascii=False)[:1400])"; }
rm -f $OV $PROJ/Saved/BlSync/status_area_04_03.json
S=$((RANDOM + 500)); P=""
for k in SteppedSlabTowerA06_89e92b38 CitySpireTower_c53c2bcc ImperialExchangeTowerE01_d562fa3e TwinWingFinanceE02_84b722e9; do
  python3 perturb_glb.py data/meshes/CBD_$k.glb data/rt/meshes/M28_${k%%_*}.glb $S > /dev/null; S=$((S + 1)); P="$P ${k%%_*}"; done
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
b "{\"action\": \"watch\", \"overrides\": [\"$OV\"], \"interval\": 0.1}" 60
q gap_rec.py '{"mode": "start"}' 60
python3 - $P <<'PY'
import json, time, os, hashlib, sys
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
J = "/workspace/jobs/look-blsync-20261009-01/data/"; p = J + "rt/matasync_area_04_03_overrides.json"
sha = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
ks = sys.argv[1:]
meshes = {f"M28_{k}": {"glb": J + f"rt/meshes/M28_{k}.glb", "sha256": sha(J + f"rt/meshes/M28_{k}.glb")} for k in ks}
inst = {f"area_04_03_m28_{k}": {"part": f"M28_{k}", "era": "both", "src": "#28 materials test", "pos": [500 + 80 * i, -650, 0],
                               "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]} for i, k in enumerate(ks)}
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": sha(PL), "rev": 1, "written": time.time(),
      "instances": inst, "meshes": meshes}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p); print("rev 1:", ks)
PY
R=$PROJ/Saved/BlSync/status_area_04_03.json; t0=$(date +%s.%N); seen=""
for i in $(seq 1 900); do
  line=$(python3 -c "import json; s=json.load(open('$R')); print(s.get('rev'), s.get('complete'), s.get('counts'), 'pending', s.get('pending_meshes'), 'meshes', [(m.get('part'), m.get('glb_materials'), m.get('queued_s'), m.get('import_s')) for m in s.get('meshes', [])], 'errors', s.get('errors'), 'unmapped', s.get('unmapped_slots'))" 2>/dev/null)
  if [ -n "$line" ] && [ "$line" != "$seen" ]; then printf "%6.1f s  %s\n" $(echo "$(date +%s.%N) - $t0" | bc) "$line" | cut -c1-700; seen="$line"; fi
  echo "$line" | grep -q "^1 True" && break; sleep 0.2; done
q gap_rec.py '{"mode": "stop"}' 60
b '{"action": "materials", "name": "A0403", "inst": ["area_04_03_m28_SteppedSlabTowerA06", "area_04_03_m28_TwinWingFinanceE02"]}' 60
b '{"action": "detach"}' 120
