set -uo pipefail
# 10-10: renou-placements/1 optional row fields (layer, recipe, group, pair, event, lock, tags) and an unknown field:
# attach and apply as before; where() reports the optional fields.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
SRC=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
PL=$J/data/rt/fields_area_04_03_placements.json
OV=$J/data/rt/fields_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:500])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(d.get('wall_s'), 's:', json.dumps(r, ensure_ascii=False)[:500])"; }
python3 - "$SRC" "$PL" "$OV" <<'PY'
import json, sys, time, hashlib, os
src, pl, ov = sys.argv[1:]
d = json.load(open(src))
for r in d["instances"]:
    if r["id"] in ("area_04_03_000646", "area_04_03_000647"):
        r.update(layer="HERO", recipe="V2", group="g001", pair=r["id"].replace("area", "past"), event="E-1",
                 lock="hand", tags=["helper"])
    if r["id"] == "area_04_03_000648":
        r["x_future"] = {"a": [1, 2, 3]}
open(pl, "w").write(json.dumps(d))
o = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": hashlib.sha256(open(pl, "rb").read()).hexdigest(),
     "rev": 1, "written": time.time(), "instances": {"area_04_03_000646": {"pos": [25.0, 0, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]},
                                                    "area_04_03_bl_new1": {"part": next(r for r in d["instances"] if r["id"] == "area_04_03_000646")["part"],
                                                                           "era": "both", "src": "fields test", "pos": [700, -700, 0],
                                                                           "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1],
                                                                           "layer": "L5", "group": "g9", "tags": ["helper"]}}}
open(ov + ".tmp", "w").write(json.dumps(o)); os.replace(ov + ".tmp", ov)
print("table with optional fields on 2 rows and x_future on 1 row")
PY
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 120
b '{"action": "where", "name": "A0403", "inst": "area_04_03_000646"}' 30
b '{"action": "where", "name": "A0403", "inst": "area_04_03_000648"}' 30
b '{"action": "where", "name": "A0403", "inst": "area_04_03_bl_new1"}' 30
q bl_sync_verify.py '{"name": "A0403", "all": true}' 60
b '{"action": "detach"}' 120
