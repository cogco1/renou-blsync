#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""人偶之心 · Blender→UE 实时预览 test copy: send one lk_session request to the test editor and wait (视效's live_req.py
with the test project path).   python3 req.py <script.py> '<json>' [timeout_s]      python3 req.py quit"""
import json, os, sys, time, uuid
from pathlib import Path

CTRL = Path(os.environ.get("PROJ", "/workspace/jobs/look-blsync-20261009-01/BlSyncTest")) / "Saved" / "LookDevCtrl"
script = sys.argv[1]
raw = sys.argv[2] if len(sys.argv) > 2 else "{}"
payload = json.loads(Path(raw[1:]).read_text(encoding="utf-8") if raw.startswith("@") else raw)
timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 600
done = {"lk_shot.py": CTRL / "shot_done.json"}.get(script)
if done:
    done.unlink(missing_ok=True)
rid = str(uuid.uuid4())
body = dict(payload, id=rid, action="quit") if script == "quit" else dict(payload, id=rid, script=script)
tmp = CTRL / "request.tmp"
tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
tmp.replace(CTRL / "request.json")
t0 = time.time()
res = None
while time.time() - t0 < timeout:
    try:
        r = json.loads((CTRL / "result.json").read_text(encoding="utf-8-sig"))
    except Exception:
        r = None
    if r and r.get("id") == rid and r.get("status") != "running":
        res = r
        break
    time.sleep(0.1)
if res is None:
    print(json.dumps({"status": "timeout"}))
    sys.exit(1)
if done and res.get("status") == "async":
    while time.time() - t0 < timeout and not done.exists():
        time.sleep(0.2)
    res["done"] = json.loads(done.read_text(encoding="utf-8")) if done.exists() else "timeout"
res["wall_s"] = round(time.time() - t0, 2)
print(json.dumps(res, ensure_ascii=False, default=str))
sys.exit(0 if res.get("status") in ("done", "async", "quitting") else 1)
