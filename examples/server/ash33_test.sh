set -uo pipefail
# Ash 10-10 on #33: every receipt (success and error) names its batch and lands in status_<batch>.json too.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/ash33_area_04_03_overrides.json
S=$PROJ/Saved/BlSync
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:300])"; }
w() {  # rev, base sha ok?
python3 - "$1" "$2" <<'PY'
import json, time, os, hashlib, sys
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
p = "/workspace/jobs/look-blsync-20261009-01/data/rt/ash33_area_04_03_overrides.json"
base = hashlib.sha256(open(PL, "rb").read()).hexdigest() if sys.argv[2] == "ok" else "0" * 64
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": base, "rev": int(sys.argv[1]), "written": time.time(),
      "instances": {"area_04_03_000646": {"pos": [25.0, 0, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}}}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p)
PY
}
show() { for f in status.json status_area_04_03.json; do python3 -c "import json; s=json.load(open('$S/$f')); print('  $f:', 'batch', s.get('batch'), 'rev', s.get('rev'), 'error', (s.get('error') or '')[-80:].strip().replace(chr(10), ' '))"; done; }
rm -f $S/status.json $S/status_area_04_03.json
q bl_sync.py '{"action": "reload"}' 120
q bl_sync.py '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
q bl_sync.py "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
q bl_sync.py "{\"action\": \"watch\", \"overrides\": [\"$OV\"], \"interval\": 0.1}" 60
echo "== a good file"; w 1 ok; sleep 2; show
echo "== a file for another table version (UE refuses it)"; w 2 bad; sleep 2; show
q bl_sync.py '{"action": "detach"}' 120
