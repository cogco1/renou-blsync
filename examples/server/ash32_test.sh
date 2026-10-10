set -uo pipefail
# Ash 10-10 on #32: (1) frame / remove never move or delete a camera bl_sync did not make; (2) a slot that showed the
# placeholder is reported again after the part's mesh changes (it used to be carried silently).
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/ash32_area_04_03_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:600])"; }
python3 perturb_glb.py data/rt/meshes/P28_T170.glb data/rt/meshes/A32_T170_v2.glb $((RANDOM + 5000)) > /dev/null
w() {
python3 - "$1" "$2" <<'PY'
import json, time, os, hashlib, sys
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
J = "/workspace/jobs/look-blsync-20261009-01/data/"; p = J + "rt/ash32_area_04_03_overrides.json"; g = J + "rt/meshes/" + sys.argv[2]
sha = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": sha(PL), "rev": int(sys.argv[1]), "written": time.time(),
      "instances": {"area_04_03_a32": {"part": "A32_T170", "era": "both", "src": "ash32", "pos": [600, -600, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}},
      "meshes": {"A32_T170": {"glb": g, "sha256": sha(g)}}}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p)
PY
}
q bl_sync.py '{"action": "reload"}' 120
q bl_sync.py '{"action": "detach"}' 120
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
q bl_sync.py "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120
echo "== 1. a camera of someone else's labelled CAM_BLSYNC"
q user_cam.py '{"mode": "spawn"}' 60
q bl_sync.py '{"action": "frame", "inst": "area_04_03_000646", "cam": "BLSYNC"}' 60
q user_cam.py '{"mode": "check"}' 60
q bl_sync.py '{"action": "frame", "cam": "BLSYNC", "remove": true}' 60
q user_cam.py '{"mode": "check"}' 60
q user_cam.py '{"mode": "delete"}' 60
echo "== 2. new part with unmapped slots, then the same part with new geometry"
w 1 P28_T170.glb
q bl_sync.py "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 300
for i in $(seq 1 120); do python3 -c "import json,sys; s=json.load(open('$PROJ/Saved/BlSync/status.json')); sys.exit(0 if s.get('complete', True) and s.get('rev') == 1 else 1)" 2>/dev/null && break; sleep 1; done   # async import (#28): wait for the complete receipt
python3 -c "import json; s=json.load(open('$PROJ/Saved/BlSync/status.json')); print('rev', s.get('rev'), 'unmapped', s.get('unmapped_slots'))"
w 2 A32_T170_v2.glb
q bl_sync.py "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 300
for i in $(seq 1 120); do python3 -c "import json,sys; s=json.load(open('$PROJ/Saved/BlSync/status.json')); sys.exit(0 if s.get('complete', True) and s.get('rev') == 2 else 1)" 2>/dev/null && break; sleep 1; done   # async import (#28): wait for the complete receipt
python3 -c "import json; s=json.load(open('$PROJ/Saved/BlSync/status.json')); print('rev', s.get('rev'), 'unmapped', s.get('unmapped_slots'), 'slots', {k: v[1] for m in (s.get('meshes') or []) for k, v in (m.get('slots') or {}).items()})"
q bl_sync.py '{"action": "detach"}' 120
