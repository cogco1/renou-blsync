set -uo pipefail
J=/workspace/jobs/look-blsync-20261009-01; cd $J
mkdir -p $J/data/rt && chmod 777 $J/data/rt
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:600])"; }
EXIST=$(python3 req.py bl_sync.py '{"action": "hosts", "prefix": "INST_A0104"}' 60 | python3 -c "import json,sys; print(len(json.load(sys.stdin)['report']['actors']))")
if [ "$EXIST" = 0 ]; then
  q ct_placements.py '{"placements": "/workspace/shared/eng-inst/u20b_r1/area_01_04/area_01_04_placements.json", "name": "A0104", "dest": "/Game/Inst/A0104", "keep_materials": true, "skip_ground": true, "map": "/Game/BlSync/L_Test", "save": true}' 1800
fi
q bl_sync.py '{"action": "attach", "placements": "/workspace/shared/eng-inst/u20b_r1/area_01_04/area_01_04_placements.json", "name": "A0104"}' 300
q bl_sync.py "{\"action\": \"watch\", \"overrides\": [\"$J/data/test/area_04_03_overrides.json\", \"$J/data/rt/area_01_04_overrides.json\"], \"interval\": 0.1}" 60
