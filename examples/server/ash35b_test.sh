set -uo pipefail
# Ash 10-10 re-review on #35: a failure INSIDE finish_mesh() (after the part was picked) or in the re-apply after the
# meshes are in must leave the work retryable: the part stays pending / the re-apply is owed, and the retry finishes it.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/ash35b_area_04_03_overrides.json; R=$PROJ/Saved/BlSync/status_area_04_03.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:300])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:300])"; }
show() { python3 -c "import json,time; s=json.load(open('$R')); print('  receipt rev', s.get('rev'), 'complete', s.get('complete'), 'pending', s.get('pending_meshes'), 'counts', s.get('counts'), 'error', (s.get('error') or '').strip().splitlines()[-1:])"; }
wait_complete() { for i in $(seq 1 40); do python3 -c "import json,sys; s=json.load(open('$R')); sys.exit(0 if s.get('complete') and s.get('rev') == $1 and not s.get('error') else 1)" 2>/dev/null && break; sleep 1; done; }
w() {
python3 - "$1" "$2" <<'PY'
import json, time, os, hashlib, sys
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
J = "/workspace/jobs/look-blsync-20261009-01/data/"; p = J + "rt/ash35b_area_04_03_overrides.json"; g = J + "rt/meshes/" + sys.argv[2]
sha = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
part = sys.argv[2][:-4]
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": sha(PL), "rev": int(sys.argv[1]), "written": time.time(),
      "instances": {"area_04_03_a35b": {"part": part, "era": "both", "src": "ash35b", "pos": [600, -600, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}},
      "meshes": {part: {"glb": g, "sha256": sha(g)}}}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p)
PY
}
for k in 1 2; do python3 perturb_glb.py data/rt/meshes/P28_T150.glb data/rt/meshes/B35_T150_$k.glb $((RANDOM + 9000)) > /dev/null; done
rm -f $R
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120 > /dev/null
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120 > /dev/null
b "{\"action\": \"watch\", \"overrides\": [\"$OV\"], \"interval\": 0.1}" 60 > /dev/null
echo "== 1. finish_mesh() fails after the part was picked"
q finish_fault.py '{"name": "A0403", "mode": "mesh_on", "retry_s": 6}' 60
w 1 B35_T150_1.glb; sleep 12; show
q finish_fault.py '{"name": "A0403", "mode": "off", "retry_s": 6}' 60
wait_complete 1; show
echo "== 2. the re-apply after the mesh is in fails"
q finish_fault.py '{"name": "A0403", "mode": "apply_on", "retry_s": 6}' 60
w 2 B35_T150_2.glb; sleep 12; show
q finish_fault.py '{"name": "A0403", "mode": "off", "retry_s": 6}' 60
wait_complete 2; show
b '{"action": "where", "name": "A0403", "inst": "area_04_03_a35b"}' 30
q finish_fault.py '{"name": "A0403", "mode": "off", "retry_s": 60}' 60
b '{"action": "detach"}' 120 > /dev/null
