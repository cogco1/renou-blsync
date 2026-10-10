set -uo pipefail
# Ash 10-10 on #36: attaching an attached batch again with a table that cannot be built (broken JSON, a table that does
# not match the level) fails and leaves the old batch and its preview exactly as they were; restore twice is a no-op.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/ash36_area_04_03_overrides.json; BROKEN=$J/data/rt/ash36_broken_placements.json; SHIFTED=$J/data/rt/ash36_shifted_placements.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[-260:] if isinstance(r, str) else json.dumps(r, ensure_ascii=False)[:300])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(r.strip().splitlines()[-1][:200] if isinstance(r, str) else json.dumps(r, ensure_ascii=False)[:300])"; }
state() { q hism_count.py '{}' 60; b '{"action": "where", "name": "A0403", "inst": "area_04_03_000646"}' 30; q bl_sync_verify.py '{"name": "A0403", "all": true}' 60; }
python3 - "$PL" "$OV" "$BROKEN" "$SHIFTED" <<'PY'
import json, time, os, hashlib, sys
pl, ov, broken, shifted = sys.argv[1:]
d = json.load(open(pl))
src = next(r for r in d["instances"] if r["id"] == "area_04_03_000646")
o = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": hashlib.sha256(open(pl, "rb").read()).hexdigest(), "rev": 1,
     "written": time.time(), "instances": {"area_04_03_000646": {"pos": [25.0, 0, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]},
                                           "area_04_03_000647": {"deleted": True},
                                           "area_04_03_a36": {"part": src["part"], "era": "both", "src": "ash36", "pos": [700, -700, 0],
                                                              "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}}}
json.dump(o, open(ov, "w"))
open(broken, "w").write(json.dumps(d)[:5000])                  # cut in the middle: not JSON
for r in d["instances"]:
    r["pos"] = [r["pos"][0] + 100.0, r["pos"][1], r["pos"][2]]
json.dump(d, open(shifted, "w"))                               # another layout: does not match the level
PY
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120 > /dev/null
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120 > /dev/null
b "{\"action\": \"watch\", \"overrides\": [\"$OV\"], \"interval\": 0.1}" 60 > /dev/null
sleep 1; echo "== preview on (646 +25 m, 647 deleted, one added)"; state
echo "== attach A0403 again with a broken table: error, preview untouched"
b "{\"action\": \"attach\", \"placements\": \"$BROKEN\", \"name\": \"A0403\"}" 120; sleep 1; state
echo "== attach A0403 again with a table that does not match the level: error, preview untouched"
b "{\"action\": \"attach\", \"placements\": \"$SHIFTED\", \"name\": \"A0403\"}" 120; sleep 1; state
echo "== attach A0403 again with the right table: replaced, the watch applies the file again"
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120 > /dev/null; sleep 1; state
echo "== restore twice: already attached"
b '{"action": "restore"}' 120; b '{"action": "restore"}' 120
b '{"action": "detach"}' 120 > /dev/null
