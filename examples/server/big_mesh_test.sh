set -uo pipefail
# IC01 (5 M triangles, 400 MB GLB) through the real path: async import as a new part, editor tick gaps, receipt.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/big_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:600])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(d.get('wall_s'), 's:', json.dumps(r, ensure_ascii=False)[:300])"; }
python3 perturb_glb.py data/meshes/NS3B_NS_IC01_8d94abd0.glb data/rt/meshes/BIG2_IC01.glb $((RANDOM + 3000)) > /dev/null
python3 - <<'PY'
import json, time, os, hashlib
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
J = "/workspace/jobs/look-blsync-20261009-01/data/"; p = J + "rt/big_area_04_03_overrides.json"; g = J + "rt/meshes/BIG2_IC01.glb"
sha = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": sha(PL), "rev": 1, "written": time.time(),
      "instances": {"area_04_03_big1": {"part": "BIG2_IC01", "era": "both", "src": "big mesh test", "pos": [600, -600, 0],
                                        "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]},
                    "area_04_03_000646": {"pos": [25.0, 0, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}},
      "meshes": {"BIG2_IC01": {"glb": g, "sha256": sha(g)}}}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p)
PY
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
R=$PROJ/Saved/BlSync/status_area_04_03.json; rm -f $R
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
q gap_rec.py '{"mode": "start"}' 60
t0=$(date +%s)
b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 120
for i in $(seq 1 120); do python3 -c "import json,sys; s=json.load(open('$R')); sys.exit(0 if s.get('complete') else 1)" 2>/dev/null && break; sleep 3; done
echo "complete after $(( $(date +%s) - t0 )) s"
python3 -c "import json; s=json.load(open('$R')); print(s.get('counts'), [(m['part'], m.get('triangles'), m.get('import_s')) for m in s.get('meshes', [])], s.get('errors'))"
q gap_rec.py '{"mode": "stop"}' 60
b '{"action": "detach"}' 120
