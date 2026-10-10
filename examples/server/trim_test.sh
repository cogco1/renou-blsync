set -uo pipefail
J=/workspace/jobs/look-blsync-20261009-01; cd $J
VEG=/workspace/shared/eng-inst/u20b_r1/vegetation/peninsula/veg_peninsula_present_placements.json
OV=$J/data/test/veg_peninsula_present_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:500])"; }
q bl_sync.py '{"action": "reload"}' 60
q bl_sync.py "{\"action\": \"attach\", \"kind\": \"veg\", \"placements\": \"$VEG\", \"veg\": \"TEST\"}" 600
q bl_sync.py "{\"action\": \"apply\", \"overrides\": \"$OV\"}" 120
q bl_sync.py '{"action": "detach"}' 120
q bl_sync.py '{"action": "hosts", "prefix": "VEG_TEST"}' 60
echo "== buildings: new part -> new HISM, then reset"
q bl_sync.py '{"action": "attach", "placements": "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json", "name": "A0403"}' 300
q bl_sync.py "{\"action\": \"watch\", \"overrides\": \"$J/data/test/area_04_03_overrides.json\", \"interval\": 0.1}" 60
blender -b --factory-startup --disable-autoexec --python-exit-code 1 --python $J/mat_skip_test.py 2>&1 | grep -E '^MATSKIP|Traceback'
sleep 1; python3 -c "import json; s=json.load(open('$J/BlSyncTest/Saved/BlSync/status.json')); print('last status:', {k: s.get(k) for k in ('rev','counts','trimmed','save_guard')})"
q bl_sync.py '{"action": "attach", "placements": "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json", "name": "A0403"}' 300
