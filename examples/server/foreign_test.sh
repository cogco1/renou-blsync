set -uo pipefail
# changes made in UE by another tool (视效's lk_ns_hide, 10-09): attach tolerates them, overrides win and say so,
# reapply puts the override back after a restore that brought back a deleted instance.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/foreign_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:600])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(d.get('wall_s'), 's:', json.dumps(r, ensure_ascii=False)[:600])"; }
rm -f $OV
echo "== reload, level, clean attach"
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
echo "== another tool sinks 000085 and 000095 (not in any override), then bl_sync is attached again"
q foreign_edit.py '{"name": "A0403", "inst": "area_04_03_000085", "mode": "sink"}' 60
q foreign_edit.py '{"name": "A0403", "inst": "area_04_03_000095", "mode": "sink"}' 60
b '{"action": "detach"}' 120
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
echo "== strict attach still refuses"
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403S\", \"strict\": true}" 120
echo "== override: delete 000646, move 000095 (one of the sunk ones) 5 m"
python3 - <<'PY'
import json, time, os, hashlib
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
p = "/workspace/jobs/look-blsync-20261009-01/data/rt/foreign_area_04_03_overrides.json"
pl = {i["id"]: i for i in json.load(open(PL))["instances"]}
x, y, z = pl["area_04_03_000095"]["pos"]
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": hashlib.sha256(open(PL, "rb").read()).hexdigest(),
      "rev": 1, "written": time.time(),
      "instances": {"area_04_03_000646": {"deleted": True},
                    "area_04_03_000095": {"pos": [x, y + 5.0, z], "quat_wxyz": pl["area_04_03_000095"]["quat"] if "quat" in pl["area_04_03_000095"] else pl["area_04_03_000095"]["quat_wxyz"],
                                          "scale": pl["area_04_03_000095"].get("scale", 1)}}}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p)
PY
b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 120
echo "== a restore shows 000646 again at scale 1 (as lk_ns_hide's record would)"
q foreign_edit.py '{"name": "A0403", "inst": "area_04_03_000646", "mode": "show"}' 60
q bl_sync_verify.py '{"name": "A0403", "all": true, "full": true}' 60
echo "== apply again: nothing changes (bl_sync thinks 000646 is hidden)"
b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 120
echo "== reapply"
b '{"action": "reapply", "name": "A0403"}' 120
q bl_sync_verify.py '{"name": "A0403", "all": true, "full": true}' 60
echo "== detach: 000085 is still where the other tool put it (bl_sync never named it)"
b '{"action": "detach"}' 120
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
q foreign_edit.py '{"name": "A0403", "inst": "area_04_03_000085", "mode": "show"}' 60
b '{"action": "detach"}' 120
