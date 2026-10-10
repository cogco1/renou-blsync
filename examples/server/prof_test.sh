set -uo pipefail
# a north-slope-sized apply on the test editor (hide 400, add 250 copies of existing parts, move 50), profiled:
# first apply (from the table), then the same file again after a suspend / resume (the 10-10 01:19 case).
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/prof_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "
import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d))
if isinstance(r, dict) and 'tottime' in r:
    print('wall', r['wall_s'], 's', r['counts'], 'conflicts', r['conflicts'])
    print('  -- by own time'); [print('  ', l) for l in r['tottime'][:12]]
    print('  -- cumulative'); [print('  ', l) for l in r['cumulative'][:16]]
else: print(json.dumps(r, ensure_ascii=False)[:400])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(d.get('wall_s'), 's:', json.dumps(r, ensure_ascii=False)[:200])"; }
python3 - <<'PY'
import json, time, os, hashlib, random
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
p = "/workspace/jobs/look-blsync-20261009-01/data/rt/prof_area_04_03_overrides.json"
rows = json.load(open(PL))["instances"]
random.seed(7)
ids = [r["id"] for r in rows]
random.shuffle(ids)
inst = {}
for iid in ids[:400]:
    inst[iid] = {"deleted": True}
for iid in ids[400:450]:
    r = next(x for x in rows if x["id"] == iid)
    inst[iid] = {"pos": [r["pos"][0] + 3, r["pos"][1], r["pos"][2]], "quat_wxyz": r.get("quat_wxyz", [1, 0, 0, 0]), "scale": [1, 1, 1]}
for k in range(250):
    r = rows[k % len(rows)]
    inst[f"area_04_03_prof{k:04d}"] = {"part": r["part"], "era": r.get("era", "both"), "src": "prof", "quat_wxyz": [1, 0, 0, 0],
                                       "pos": [r["pos"][0] + 500 + (k % 20) * 30, r["pos"][1] - 500 - (k // 20) * 30, r["pos"][2]], "scale": [1, 1, 1]}
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": hashlib.sha256(open(PL, "rb").read()).hexdigest(),
      "rev": 1, "written": time.time(), "instances": inst, "meshes": {}}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p); print("override: hide 400, move 50, add 250")
PY
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
echo "== first apply"
q prof_apply.py "{\"name\": \"A0403\", \"overrides\": \"$OV\"}" 600
echo "== suspend, then the same file again (as resume does)"
b '{"action": "suspend"}' 300
b '{"action": "resume"}' 60
q prof_apply.py "{\"name\": \"A0403\", \"overrides\": \"$OV\"}" 600
b '{"action": "detach"}' 300
