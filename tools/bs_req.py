#!/usr/bin/env python3
"""Blender→UE 实时预览: one request through bl_sync's OWN control channel (Saved/BlSync/request.json -> result.json),
not through 视效's lk_session channel. Works once bl_sync_core is loaded in the editor (after any bl_sync.py request,
e.g. the "restore" that 视效's restart script sends).
    PROJ=/workspace/guest/look-ue-20261008/HarborLookMS python3 bs_req.py '{"action": "status"}' [timeout_s]"""
import json, os, sys, time, uuid
from pathlib import Path

CTRL = Path(os.environ.get("PROJ", "/workspace/guest/look-ue-20261008/HarborLookMS")) / "Saved" / "BlSync"
req = json.loads(sys.argv[1] if len(sys.argv) > 1 else '{"action": "status"}')
timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 600
req["id"] = str(uuid.uuid4())
tmp = CTRL / "request.tmp"
tmp.write_text(json.dumps(req, ensure_ascii=False), encoding="utf-8")
tmp.replace(CTRL / "request.json")
t0 = time.time()
while time.time() - t0 < timeout:
    try:
        r = json.loads((CTRL / "result.json").read_text(encoding="utf-8"))
    except Exception:
        r = {}
    if r.get("id") == req["id"]:
        r["wall_s"] = round(time.time() - t0, 2)
        print(json.dumps(r, ensure_ascii=False, default=str))
        sys.exit(0 if r.get("status") == "done" else 1)
    time.sleep(0.1)
print(json.dumps({"status": "timeout", "hint": "is bl_sync_core loaded? send bl_sync.py {action: restore} once"}))
sys.exit(1)
