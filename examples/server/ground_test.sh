set -uo pipefail
J=/workspace/jobs/look-blsync-20261009-01; cd $J
T=/workspace/shared/eng-inst/u20b_r1/ground_core/terrain/CITY_terrain_2.gltf
OV=$J/data/test/GCTEST_overrides.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:1200])"; }
q bl_sync.py '{"action": "reload"}' 60
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
EXIST=$(python3 req.py bl_sync.py '{"action": "hosts", "prefix": "INST_GCTEST"}' 60 | python3 -c "import json,sys; print(len(json.load(sys.stdin)['report']['actors']))")
if [ "$EXIST" = 0 ]; then
  q ct_placements.py "{\"name\": \"GCTEST\", \"dest\": \"/Game/Inst/GCTEST\", \"ground_glbs\": [\"$T\"], \"keep_materials\": true, \"map\": \"/Game/BlSync/L_Test\", \"save\": true}" 1800
fi
TID=$(python3 req.py bl_sync.py '{"action": "hosts", "prefix": "INST_GCTEST"}' 60 | python3 -c "
import json,sys,re
r=[a['label'] for a in json.load(sys.stdin)['report']['actors'] if a['label'].endswith('_LOD0')]
print(re.sub(r'_LOD0$','',sorted(r)[len(r)//2]))")
echo "tile: $TID"
mkdir -p $J/data/test/meshes
blender -b --factory-startup --disable-autoexec --python-exit-code 1 --python $J/tile_edit.py -- $T $TID $J/data/test/meshes/${TID}_up5.glb 2>&1 | grep -E "^TILEEDIT|Traceback|Error"
q bl_sync.py '{"action": "attach", "kind": "ground", "name": "GCTEST"}' 300
python3 - "$TID" <<'PY'
import json, time, os, hashlib, sys
tid=sys.argv[1]; J="/workspace/jobs/look-blsync-20261009-01/"
g=J+f"data/test/meshes/{tid}_up5.glb"
ov={"schema":"renou-overrides/1","batch":"GCTEST","rev":int(time.time()),"written":time.time(),"instances":{},
    "meshes":{tid:{"glb":g,"sha256":hashlib.sha256(open(g,"rb").read()).hexdigest()}}}
p=J+"data/test/GCTEST_overrides.json"; open(p+".tmp","w").write(json.dumps(ov)); os.replace(p+".tmp",p)
PY
q bl_sync.py "{\"action\": \"apply\", \"overrides\": \"$OV\"}" 600
stat -c "%A %n" $J/BlSyncTest/Content/BlSync/L_Test.umap
python3 - <<'PY'
import json, time, os
p="/workspace/jobs/look-blsync-20261009-01/data/test/GCTEST_overrides.json"
ov=json.load(open(p)); ov.update(rev=ov["rev"]+1, written=time.time(), meshes={})
open(p+".tmp","w").write(json.dumps(ov)); os.replace(p+".tmp",p)
PY
q bl_sync.py "{\"action\": \"apply\", \"overrides\": \"$OV\"}" 120
q bl_sync.py '{"action": "detach"}' 120
stat -c "%A %n" $J/BlSyncTest/Content/BlSync/L_Test.umap
