set -uo pipefail
# Ash 10-10 on #35: a finish that fails writes a final error receipt (batch, rev, pending meshes), stays retryable,
# is retried after FINISH_RETRY_S, and at once when a new version of the file comes.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/ash35_area_04_03_overrides.json; R=$PROJ/Saved/BlSync/status_area_04_03.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:300])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:300])"; }
show() { python3 -c "import json,time; s=json.load(open('$R')); print('  receipt batch', s.get('batch'), 'rev', s.get('rev'), 'complete', s.get('complete'), 'pending', s.get('pending_meshes'), 'error', (s.get('error') or '').strip().splitlines()[-1:] , 'age', round(time.time() - (s.get('t') or s.get('applied_at') or 0), 1))"; }
python3 perturb_glb.py data/rt/meshes/P28_T150.glb data/rt/meshes/A35_T150.glb $((RANDOM + 7000)) > /dev/null
python3 perturb_glb.py data/rt/meshes/P28_T190.glb data/rt/meshes/A35_T190.glb $((RANDOM + 7000)) > /dev/null
w() {
python3 - "$1" "$2" <<'PY'
import json, time, os, hashlib, sys
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
J = "/workspace/jobs/look-blsync-20261009-01/data/"; p = J + "rt/ash35_area_04_03_overrides.json"; g = J + "rt/meshes/" + sys.argv[2]
sha = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
part = "A35_" + sys.argv[2][4:8]
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": sha(PL), "rev": int(sys.argv[1]), "written": time.time(),
      "instances": {"area_04_03_a35": {"part": part, "era": "both", "src": "ash35", "pos": [600, -600, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}},
      "meshes": {part: {"glb": g, "sha256": sha(g)}}}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p)
PY
}
rm -f $R
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120 > /dev/null
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120 > /dev/null
q finish_fault.py '{"name": "A0403", "mode": "on", "retry_s": 8}' 60
b "{\"action\": \"watch\", \"overrides\": [\"$OV\"], \"interval\": 0.1}" 60 > /dev/null
echo "== rev 1 (new part, import), finish fails"; w 1 A35_T150.glb; sleep 12; show
echo "== rev 2 (another new part) while failing: a new version retries at once (and fails again)"; w 2 A35_T190.glb; sleep 12; show
echo "== the fault goes; the next retry (<= 8 s) finishes rev 2"
q finish_fault.py '{"name": "A0403", "mode": "off", "retry_s": 8}' 60
for i in $(seq 1 40); do python3 -c "import json,sys; s=json.load(open('$R')); sys.exit(0 if s.get('complete') and s.get('rev') == 2 else 1)" 2>/dev/null && break; sleep 1; done; show
python3 -c "import json; s=json.load(open('$R')); print('  counts', s.get('counts'), 'meshes', [m.get('part') for m in s.get('meshes', [])])"
q finish_fault.py '{"name": "A0403", "mode": "off", "retry_s": 60}' 60
b '{"action": "detach"}' 120 > /dev/null
