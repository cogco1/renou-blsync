set -uo pipefail
# Ash 10-10 on #34: one identity (the resolved batch name) for S["batches"], session records and detach(name);
# a single detach also drops that batch's watched files; a restart does not bring a detached batch back.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/ash34_area_04_03_overrides.json; OTHER=$J/data/rt/ash34_other_overrides.json; VEG=$J/data/rt/ash34_veg_placements.json
SESS=$PROJ/Saved/BlSync/session.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:400])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:400])"; }
sess() { python3 -c "import json; s=json.load(open('$SESS')); print('  session attach', [(a.get('name'), a.get('kind')) for a in s['attach']], 'watch', [p.rsplit('/',1)[-1] for p in (s.get('watch') or {}).get('paths', [])])"; }
python3 - "$PL" "$OV" "$OTHER" "$VEG" <<'PY'
import json, time, os, hashlib, sys
pl, ov, other, veg = sys.argv[1:]
json.dump({"schema": "renou-placements/1", "coord": "blender_zup_m", "batch": "veg_test", "instances": []}, open(veg, "w"))
o = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": hashlib.sha256(open(pl, "rb").read()).hexdigest(), "rev": 1,
     "written": time.time(), "instances": {"area_04_03_000646": {"pos": [25.0, 0, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}}}
json.dump(o, open(ov, "w"))
json.dump(dict(o, batch="area_09_09"), open(other, "w"))     # another batch's file (not attached here)
PY
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
echo "== record_name: a vegetation record without name resolves to its table's batch"
q record_name_probe.py "{\"placements\": \"$VEG\"}" 60
echo "== attach the same batch twice: one session record, with its name"
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120 > /dev/null
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120 > /dev/null
b "{\"action\": \"watch\", \"overrides\": [\"$OV\", \"$OTHER\"], \"interval\": 0.1}" 60 > /dev/null
sleep 1; sess
echo "== an old unnamed vegetation record in the session; detach(veg_test) removes it"
python3 - "$SESS" "$VEG" <<'PY'
import json, sys
s = json.load(open(sys.argv[1])); s["attach"].append({"kind": "veg", "placements": sys.argv[2], "veg": "TEST"})
json.dump(s, open(sys.argv[1], "w"), indent=1)
PY
sess
b '{"action": "detach", "name": "veg_test"}' 60
sess
echo "== detach(A0403): its record and its watched file go, the other batch's file stays"
b '{"action": "detach", "name": "A0403"}' 60
sess
b '{"action": "status"}' 30
echo "== restart (reload + restore): A0403 does not come back"
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "status"}' 30
b '{"action": "unwatch"}' 30 > /dev/null
