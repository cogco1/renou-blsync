set -uo pipefail
J=/workspace/jobs/look-blsync-20261009-01; cd $J
G=/workspace/guest/look-ue-20261008
VEG=/workspace/shared/eng-inst/u20b_r1/vegetation/peninsula/veg_peninsula_present_placements.json
OV=$J/data/test/veg_peninsula_present_overrides.json
cp $G/HarborLookMS/Content/Python/ct_vegplace.py $J/BlSyncTest/Content/Python/ && chown user:users $J/BlSyncTest/Content/Python/*.py
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:900])"; }
q bl_sync.py '{"action": "reload"}' 60
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
q bl_sync.py '{"action": "hosts", "prefix": "VEG_"}' 60
# test vegetation around the CBD, slots on engine shapes (stand-ins), the same builder 视效 uses
q ct_vegplace.py "{\"placements\": [\"$VEG\"], \"map\": {\"tree_broadleaf_A\": \"/Engine/BasicShapes/Cone\", \"tree_broadleaf_B\": \"/Engine/BasicShapes/Cone\", \"tree_conifer_A\": \"/Engine/BasicShapes/Cylinder\", \"tree_conifer_B\": \"/Engine/BasicShapes/Cylinder\", \"shrub_A\": \"/Engine/BasicShapes/Sphere\", \"shrub_B\": \"/Engine/BasicShapes/Sphere\"}, \"centres\": [[500, -300]], \"radius_m\": 600, \"name\": \"TEST\"}" 600
q bl_sync.py "{\"action\": \"attach\", \"kind\": \"veg\", \"placements\": \"$VEG\", \"veg\": \"TEST\"}" 600
python3 - <<'PY'
import json, time, os, hashlib
VEG="/workspace/shared/eng-inst/u20b_r1/vegetation/peninsula/veg_peninsula_present_placements.json"
d=json.load(open(VEG,encoding="utf-8-sig"))
near=[i for i in d["instances"] if (i["pos"][0]-500)**2+(i["pos"][1]+300)**2 < 300**2]
pick={s:[i for i in near if i["src"]==s][:3] for s in ("tree_broadleaf_A","shrub_A")}
inst={}
for i in pick["tree_broadleaf_A"][:2]: inst[i["id"]]={"deleted": True}
for i in pick["shrub_A"][:2]: inst[i["id"]]={"pos":[i["pos"][0]+5,i["pos"][1],i["pos"][2]],"quat_wxyz":i["quat_wxyz"],"scale":[i["scale"]]*3}
t0=pick["tree_broadleaf_A"][2]
inst["veg_peninsula_present_bl000001"]={"part":"tree_broadleaf_A","src":"tree_broadleaf_A","era":"present","pos":[t0["pos"][0]+8,t0["pos"][1]+8,t0["pos"][2]],"quat_wxyz":[1,0,0,0],"scale":[1,1,1]}
inst["veg_peninsula_present_bl000002"]={"part":"tree_conifer_B","src":"tree_conifer_B","era":"present","pos":[t0["pos"][0]-8,t0["pos"][1]-8,t0["pos"][2]],"quat_wxyz":[1,0,0,0],"scale":[1,1,1]}
ov={"schema":"renou-overrides/1","batch":d["batch"],"base_sha256":hashlib.sha256(open(VEG,"rb").read()).hexdigest(),"rev":1,"written":time.time(),"instances":inst}
p="/workspace/jobs/look-blsync-20261009-01/data/test/veg_peninsula_present_overrides.json"
open(p+".tmp","w").write(json.dumps(ov)); os.replace(p+".tmp",p)
json.dump({"deleted":[k for k,v in inst.items() if v.get("deleted")],"moved":[i["id"] for i in pick["shrub_A"][:2]]}, open("/workspace/jobs/look-blsync-20261009-01/out/veg_test_ids.json","w"))
print("veg override written:", {k: ("deleted" if v.get("deleted") else "moved/added") for k,v in inst.items()})
PY
q bl_sync.py "{\"action\": \"apply\", \"overrides\": \"$OV\"}" 120
stat -c "%A %n" $J/BlSyncTest/Content/BlSync/L_Test.umap
q bl_sync.py "{\"action\": \"watch\", \"overrides\": [\"$OV\"], \"interval\": 0.1}" 60
echo "== suspend (UE wants to save)"
q bl_sync.py '{"action": "suspend"}' 120
stat -c "%A %n" $J/BlSyncTest/Content/BlSync/L_Test.umap
echo "== resume"
q bl_sync.py '{"action": "resume"}' 60
sleep 1.5; cat $J/BlSyncTest/Saved/BlSync/status.json; echo
stat -c "%A %n" $J/BlSyncTest/Content/BlSync/L_Test.umap
echo "== detach"
q bl_sync.py '{"action": "detach"}' 120
stat -c "%A %n" $J/BlSyncTest/Content/BlSync/L_Test.umap
echo "== re-attach must match the table again (0 cm, same matched count)"
q bl_sync.py "{\"action\": \"attach\", \"kind\": \"veg\", \"placements\": \"$VEG\", \"veg\": \"TEST\"}" 600
q bl_sync.py '{"action": "detach"}' 120
