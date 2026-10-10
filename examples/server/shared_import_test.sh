set -uo pipefail
# one import per part + GLB content, shared by every batch (folder /_LivePreview/_parts/<part>_<sha8>): the first apply
# imports; after a detach (record kept) and after a module reload (record gone, assets still there) the mesh is taken at
# once, no second import. (The test level has one batch layer, so the three rounds use the same batch.)
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/shared_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:300])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(d.get('wall_s'), 's:', json.dumps(r, ensure_ascii=False)[:300])"; }
python3 perturb_glb.py /workspace/shared/assets/TOWERS_150_250/glb/BLD_CBDHighTowerKit_T170_SpireBuffBrick.glb data/rt/meshes/SH_T170.glb $((RANDOM + 900)) > /dev/null
python3 - <<'PY'
import json, time, os, hashlib
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
J = "/workspace/jobs/look-blsync-20261009-01/data/"; p = J + "rt/shared_area_04_03_overrides.json"; g = J + "rt/meshes/SH_T170.glb"
sha = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": sha(PL), "rev": 1, "written": time.time(),
      "instances": {"area_04_03_sh1": {"part": "SH_T170", "era": "both", "src": "shared import test", "pos": [600, -600, 0],
                                       "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}},
      "meshes": {"SH_T170": {"glb": g, "sha256": sha(g)}}}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p)
PY
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
R=$PROJ/Saved/BlSync/status_area_04_03.json
for round in import record-kept after-reload; do
  name=A0403; echo "== $round"
  [ $round = after-reload ] && q bl_sync.py '{"action": "reload"}' 120
  rm -f $R
  b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"$name\"}" 120
  t0=$(date +%s.%N)
  b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"$name\"}" 120
  for i in $(seq 1 300); do python3 -c "import json,sys; s=json.load(open('$R')); sys.exit(0 if s.get('complete') else 1)" 2>/dev/null && break; sleep 0.2; done
  python3 -c "import json; s=json.load(open('$R')); print('  complete after', round($(date +%s.%N) - $t0, 1), 's', s.get('counts'), [(m['part'], m['asset'].rsplit('/', 3)[1], m.get('import_s'), m.get('seconds')) for m in s.get('meshes', [])])"
  b '{"action": "detach"}' 120
done
