#!/usr/bin/env python3
"""Blender→UE 实时预览: send ONE lk_session request only when the channel is free (视效's live editor shares it).
Free = the last request has its result and is not running, and nothing new appeared for `quiet` seconds. If the channel
does not become free within `max_wait` seconds, nothing is sent and the exit code is 3 (never queue behind somebody).
    PROJ=/workspace/guest/look-ue-20261008/HarborLookMS python3 safe_req.py bl_sync.py '{"action": "status"}' [timeout] [max_wait]
Prints the result JSON like live_req.py."""
import json, os, sys, time, uuid
from pathlib import Path

CTRL = Path(os.environ.get("PROJ", "/workspace/guest/look-ue-20261008/HarborLookMS")) / "Saved" / "LookDevCtrl"
script = sys.argv[1]
payload = json.loads(sys.argv[2] if len(sys.argv) > 2 else "{}")
timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 600
max_wait = float(sys.argv[4]) if len(sys.argv) > 4 else 120
quiet = float(os.environ.get("QUIET_S", "4"))


def read(name):
    try:
        return json.loads((CTRL / name).read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


t0, since, last = time.time(), None, None
while True:
    a, b = read("request.json"), read("result.json")
    free = a.get("id") is not None and a.get("id") == b.get("id") and b.get("status") != "running"
    key = (a.get("id"), b.get("id"), b.get("status"))
    if free and key == last:
        if since and time.time() - since >= quiet:
            break
    else:
        since = time.time() if free else None
    last = key
    if time.time() - t0 > max_wait:
        print(json.dumps({"status": "not_sent", "reason": f"channel busy for {max_wait:.0f} s",
                          "busy_with": b.get("script"), "busy_status": b.get("status")}))
        sys.exit(3)
    time.sleep(0.5)
rid = str(uuid.uuid4())
tmp = CTRL / "request.tmp"
tmp.write_text(json.dumps(dict(payload, id=rid, script=script), ensure_ascii=False), encoding="utf-8")
tmp.replace(CTRL / "request.json")
t1 = time.time()
while time.time() - t1 < timeout:
    r = read("result.json")
    if r.get("id") == rid and r.get("status") != "running":
        r["wall_s"] = round(time.time() - t1, 2)
        print(json.dumps(r, ensure_ascii=False, default=str))
        sys.exit(0 if r.get("status") in ("done", "async") else 1)
    if read("request.json").get("id") != rid and r.get("id") != rid:
        print(json.dumps({"status": "overwritten", "by": read("request.json").get("script")}))   # someone sent after us
        sys.exit(4)
    time.sleep(0.1)
print(json.dumps({"status": "timeout"}))
sys.exit(1)
