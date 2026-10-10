set -uo pipefail
# user 10-10: bl_sync keeps the last applied file before a version that clears / shrinks / rewinds it is applied.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/snap_area_04_03_overrides.json
A=$J/data/rt/archive
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:400])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(d.get('wall_s'), 's:', json.dumps(r, ensure_ascii=False)[:400])"; }
rm -f $OV; rm -f $A/snap_area_04_03_overrides__*.json
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
w() {  # rev, json of instances
python3 - "$1" "$2" <<'PY'
import json, time, os, hashlib, sys
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
p = "/workspace/jobs/look-blsync-20261009-01/data/rt/snap_area_04_03_overrides.json"
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": hashlib.sha256(open(PL, "rb").read()).hexdigest(),
      "rev": int(sys.argv[1]), "written": time.time(), "instances": json.loads(sys.argv[2]), "meshes": {}}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p)
PY
}
show() { python3 -c "import json; s=json.load(open('$PROJ/Saved/BlSync/status_area_04_03.json')); print('  receipt rev', s.get('rev'), s.get('counts'), 'snapshot_made', s.get('snapshot_made'), 'snapshot', (s.get('snapshot') or '-').rsplit('/', 1)[-1])"; ls $A 2>/dev/null | grep snap_area | sed 's/^/  archive: /'; }
M1='{"area_04_03_000646": {"pos": [25.0, 0, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}, "area_04_03_000647": {"deleted": true}}'
M2='{"area_04_03_000646": {"pos": [30.0, 0, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}, "area_04_03_000647": {"deleted": true}}'
echo "== rev 100: two overrides (first file: nothing to keep)"; w 100 "$M1"; b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 60; show
echo "== rev 101: a normal move (same ids): no snapshot"; w 101 "$M2"; b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 60; show
echo "== rev 102: cleared -> rev 101 kept"; w 102 '{}'; b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 60; show
echo "== rev 50 (back) with the overrides again -> rev 102 kept"; w 50 "$M1"; b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 60; show
echo "== the kept rev 101 is byte-identical to what was applied"; python3 -c "
import json,glob; f=sorted(glob.glob('$A/snap_area_04_03_overrides__*rev101*'))[0]; d=json.load(open(f)); print('  ', f.rsplit('/',1)[-1], d['rev'], d['instances']['area_04_03_000646']['pos'])"
b '{"action": "detach"}' 120
