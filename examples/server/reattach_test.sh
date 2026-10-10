set -uo pipefail
# restore twice and attach twice (视效's start script restores, a manual restore follows): nothing doubles.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/reattach_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:500])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(d.get('wall_s'), 's:', json.dumps(r, ensure_ascii=False)[:500])"; }
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
echo "== table count"
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
q hism_count.py '{}' 60
python3 - <<'PY'
import json, time, os, hashlib
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
p = "/workspace/jobs/look-blsync-20261009-01/data/rt/reattach_area_04_03_overrides.json"
pl = {i["id"]: i for i in json.load(open(PL))["instances"]}
src = pl["area_04_03_000646"]
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": hashlib.sha256(open(PL, "rb").read()).hexdigest(),
      "rev": 1, "written": time.time(),
      "instances": {"area_04_03_000646": {"pos": [25.0, 0, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]},
                    "area_04_03_000647": {"deleted": True},
                    "area_04_03_copy1": {"part": src["part"], "era": "both", "src": "reattach test",
                                         "pos": [700, -700, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}}}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p)
PY
b "{\"action\": \"watch\", \"overrides\": [\"$OV\"], \"interval\": 0.1}" 60
sleep 1
echo "== with the preview (one instance added)"
q hism_count.py '{}' 60
echo "== restore again (as after 视效's start script): already attached, nothing changes"
q bl_sync.py '{"action": "restore"}' 120
q hism_count.py '{}' 60
echo "== attach the same batch again: reset + replace, files applied again"
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
sleep 1
q hism_count.py '{}' 60
q bl_sync_verify.py '{"name": "A0403", "all": true}' 60
b '{"action": "where", "name": "A0403", "inst": "area_04_03_000646"}' 30
b '{"action": "detach"}' 120
echo "== after detach: back to the table count"
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
q hism_count.py '{}' 60
b '{"action": "detach"}' 120
