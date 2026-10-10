set -uo pipefail
# 10-10 01:18 live: suspend / resume took the north slope away for 45 s (every GLB hashed again, one batch per tick).
# Now: SHA cache, suspend only puts back batches in the level being saved, resume re-applies them itself.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/susp_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:500])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(d.get('wall_s'), 's:', json.dumps(r, ensure_ascii=False)[:500])"; }
python3 - <<'PY'
import json, time, os, hashlib, glob
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
J = "/workspace/jobs/look-blsync-20261009-01/data/"; p = J + "rt/susp_area_04_03_overrides.json"
glbs = sorted(glob.glob(J + "rt/meshes/P28_*.glb") + glob.glob(J + "rt/meshes/M28_*.glb"))
sha = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
meshes, inst = {}, {"area_04_03_000646": {"pos": [25.0, 0, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}}
for i, g in enumerate(glbs):
    part = "SU_" + os.path.basename(g)[:-4]
    meshes[part] = {"glb": g, "sha256": sha(g)}
    inst[f"area_04_03_su{i:02d}"] = {"part": part, "era": "both", "src": "suspend test", "pos": [500 + 80 * i, -800, 0],
                                     "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": sha(PL), "rev": 1, "written": time.time(),
      "instances": inst, "meshes": meshes}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p)
print(len(glbs), "GLBs,", round(sum(os.path.getsize(g) for g in glbs) / 1e6), "MB")
PY
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
R=$PROJ/Saved/BlSync/status_area_04_03.json; rm -f $R
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
b "{\"action\": \"watch\", \"overrides\": [\"$OV\"], \"interval\": 0.1}" 60
for i in $(seq 1 200); do python3 -c "import json,sys; s=json.load(open('$R')); sys.exit(0 if s.get('complete') else 1)" 2>/dev/null && break; sleep 1; done
python3 -c "import json; s=json.load(open('$R')); print('imported:', s.get('rev'), s.get('complete'), s.get('counts'))"
echo "== 1. the open level is saved (A0403 lives in L_Test): put back, then resume re-applies it with the SHA cache"
b '{"action": "suspend"}' 120
b '{"action": "resume"}' 120
echo "== 2. another level is saved: A0403 stays, L_Test.umap stays read-only, resume has nothing to do"
b '{"action": "suspend", "level": "/nonexistent/L_Other.umap"}' 120
ls -l $J/BlSyncTest/Content/BlSync/L_Test.umap | cut -c1-10
b '{"action": "resume"}' 120
q bl_sync_verify.py '{"name": "A0403", "all": true}' 60
echo "== 3. for comparison: the same cycle with the SHA cache emptied first"
q sha_clear.py '{}' 60
b '{"action": "suspend"}' 120
b '{"action": "resume"}' 300
b '{"action": "detach"}' 120
