#!/usr/bin/env python3
"""人偶之心 · LS01 test helper: a stand-in for the UE receiver (bl_sync_core) so the Blender plugin can be tested without
UE. Watches one override file, checks the renou-overrides/1 format against the base placements table, and writes the
same status.json UE writes ({"rev", "written", "counts", "overrides", "seconds", "applied_at", "latency_s", "errors"}).
    python3 mock_ue_receiver.py --placements area_01_04_placements.json --overrides out/area_01_04_overrides.json \
        --status out/status.json [--once]
Counts: moved / swapped / added / hidden, relative to the previous file (as UE reports them). It does not render."""
import argparse, hashlib, json, os, time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--placements", required=True)
ap.add_argument("--overrides", required=True)
ap.add_argument("--status", required=True)
ap.add_argument("--once", action="store_true")
a = ap.parse_args()
raw = Path(a.placements).read_bytes()
base_sha = hashlib.sha256(raw).hexdigest()
base = {i["id"]: i for i in json.loads(raw.decode("utf-8-sig"))["instances"]}
parts = {i["part"] for i in base.values()}
prev, sig = {}, None


def check(ov):
    errs = []
    if ov.get("schema") != "renou-overrides/1":
        errs.append(f"schema {ov.get('schema')}")
    if ov.get("base_sha256") and ov["base_sha256"] != base_sha:
        errs.append("base_sha256 does not match the placements table")
    meshes = ov.get("meshes") or {}
    for iid, e in (ov.get("instances") or {}).items():
        if e.get("deleted"):
            if iid not in base:
                errs.append(f"{iid}: deleted but not in the table")
            continue
        for k, n in (("pos", 3), ("quat_wxyz", 4)):
            if k in e and (len(e[k]) != n or not all(isinstance(v, (int, float)) for v in e[k])):
                errs.append(f"{iid}: bad {k}")
        if "quat_wxyz" in e and abs(sum(v * v for v in e["quat_wxyz"]) - 1) > 1e-4:
            errs.append(f"{iid}: quaternion not unit")
        if iid not in base and not all(k in e for k in ("part", "pos", "quat_wxyz", "era")):
            errs.append(f"{iid}: new instance needs part, pos, quat_wxyz, era")
        p = e.get("part")
        if p and p not in parts and p not in meshes:
            errs.append(f"{iid}: part {p} is neither in the batch nor in meshes")
    for p, m in meshes.items():
        g = Path(m["glb"])
        if not g.exists():
            errs.append(f"mesh {p}: {g} missing")
        elif hashlib.sha256(g.read_bytes()).hexdigest() != m.get("sha256"):
            errs.append(f"mesh {p}: sha256 mismatch")
    return errs


while True:
    try:
        st = os.stat(a.overrides)
        s = (st.st_mtime_ns, st.st_size)
    except FileNotFoundError:
        s = None
    if s and s != sig:
        sig = s
        t0 = time.time()
        ov = json.loads(Path(a.overrides).read_text(encoding="utf-8"))
        new = ov.get("instances") or {}
        counts = {}
        for iid in set(prev) | set(new):
            if prev.get(iid) == new.get(iid):
                continue
            e = new.get(iid)
            k = ("hidden" if (e is None and iid not in base) or (e or {}).get("deleted") else
                 "added" if iid not in base and iid not in prev else
                 "swapped" if (e or {}).get("part") != (prev.get(iid) or {}).get("part") else "moved")
            counts[k] = counts.get(k, 0) + 1
        prev = new
        out = {"rev": ov.get("rev"), "written": ov.get("written"), "counts": counts, "overrides": len(new),
               "errors": check(ov) or None, "seconds": round(time.time() - t0, 4), "applied_at": time.time()}
        if ov.get("written"):
            out["latency_s"] = round(out["applied_at"] - float(ov["written"]), 3)
        tmp = Path(a.status).with_suffix(".tmp")
        tmp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, a.status)
        if a.once:
            break
    time.sleep(0.05)
