"""Blender→UE 实时预览, read only: does every attached batch show exactly what its override file says?
For each instance of the last applied override (and every untouched table row of the batch): UE's instance transform
against the expected state (bl_sync_core.xf_err, cm). REQUEST {"name": "<batch>" (optional), "all": false}:
all=true also checks the untouched table rows. REPORT {batch: {"rev", "checked", "worst_cm", "bad": [...]}}."""
import bl_sync_core as core

REPORT = {}
for n, b in core.S["batches"].items():
    if REQUEST.get("name") and n != REQUEST["name"]:
        continue
    ids = set(b.applied) | (set(b.base) if REQUEST.get("all") else set())
    worst, bad, checked, hidden = 0.0, [], 0, 0
    for iid in sorted(ids):
        st = b.applied.get(iid) or b.base.get(iid)
        if st is None or st["deleted"]:
            hidden += 1
            continue
        slot = b.slot.get(iid)
        if slot is None:
            bad.append([iid, "not placed"])
            continue
        e = core.xf_err(b.comps[slot[0]].get_instance_transform(slot[1], True), st)
        worst, checked = max(worst, e), checked + 1
        if e > 1.0:
            bad.append([iid, round(e, 2)])
    REPORT[n] = {"rev": b.rev, "checked": checked, "hidden": hidden, "worst_cm": round(worst, 4), "bad": bad[:20],
                 "pending_meshes": sorted(getattr(b, "pending", {}) or {})}
