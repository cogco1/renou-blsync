set -uo pipefail
# Ash 10-10 on #37 (UE side): the first apply after a restart is still protected (last applied bytes on disk);
# a destructive version is not applied when no copy can be kept.
J=/workspace/jobs/look-blsync-20261009-01; cd $J; export PROJ=$J/BlSyncTest
PL=/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json
OV=$J/data/rt/ash37_area_04_03_overrides.json; A1=$J/data/rt/archive; A2=$PROJ/Saved/BlSync/archive; R=$PROJ/Saved/BlSync/status_area_04_03.json
q() { python3 req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(json.dumps(r, ensure_ascii=False)[:200])"; }
b() { python3 bs_req.py "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('report', d.get('error', d)); print(r.strip().splitlines()[-1][:220] if isinstance(r, str) else json.dumps({k: r.get(k) for k in ('rev', 'counts', 'snapshot_made', 'snapshot') if k in r} if 'rev' in r else r, ensure_ascii=False)[:300])"; }
w() {  # rev, "full" | "empty"
python3 - "$1" "$2" <<'PY'
import json, time, os, hashlib, sys
PL = "/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json"
p = "/workspace/jobs/look-blsync-20261009-01/data/rt/ash37_area_04_03_overrides.json"
inst = {"area_04_03_000646": {"pos": [25.0, 0, 0], "quat_wxyz": [1, 0, 0, 0], "scale": [1, 1, 1]}, "area_04_03_000647": {"deleted": True}}
ov = {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": hashlib.sha256(open(PL, "rb").read()).hexdigest(),
      "rev": int(sys.argv[1]), "written": time.time(), "instances": inst if sys.argv[2] == "full" else {}}
open(p + ".tmp", "w").write(json.dumps(ov)); os.replace(p + ".tmp", p)
PY
}
rm -f $A1/ash37_area_04_03_overrides__*.json $A2/ash37_area_04_03_overrides__*.json $PROJ/Saved/BlSync/applied/ash37_*.json
q bl_sync.py '{"action": "reload"}' 120
b '{"action": "detach"}' 120 > /dev/null
q bl_setup_level.py '{"map": "/Game/BlSync/L_Test"}' 600
b "{\"action\": \"attach\", \"placements\": \"$PL\", \"name\": \"A0403\"}" 120 > /dev/null
echo "== rev 1 (two overrides) applied"; w 1 full; b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 60
echo "== the file is cleared while the editor 'restarts' (module reload = a fresh process for bl_sync)"
w 2 empty
q bl_sync.py '{"action": "reload"}' 120
echo "== first apply after the restart: the cleared file is applied, rev 1 kept first (from Saved/BlSync/applied)"
b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 60
ls $A1 | grep ash37 | sed 's/^/  archive: /'
echo "== rev 3 full again, then rev 4 cleared while neither archive folder can be written"
w 3 full; b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 60 > /dev/null
mkdir -p $A2; chmod 555 $A1 $A2
w 4 empty; b "{\"action\": \"apply\", \"overrides\": \"$OV\", \"name\": \"A0403\"}" 60
chmod 777 $A1; chmod 755 $A2; chown user:users $A2
b '{"action": "where", "name": "A0403", "inst": "area_04_03_000646"}' 30
b '{"action": "status"}' 30 | cut -c1-200
b '{"action": "detach"}' 120 > /dev/null
