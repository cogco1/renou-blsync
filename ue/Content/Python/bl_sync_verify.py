"""Blender→UE 实时预览, read only: does every attached batch show exactly what its override file says?
For each instance of the last applied override (and every untouched table row of the batch): UE's instance transform
against the expected state (bl_sync_core.xf_err, cm). REQUEST {"name": "<batch>" (optional), "all": false, "full": false}:
all=true also checks the untouched table rows; full=true lists every mismatching id. REPORT {batch: {"rev", "checked", "worst_cm", "bad": [...]}}."""
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
            bad.append([iid, round(e, 2), "override" if iid in b.applied else "table", slot[0][1].rsplit("/", 1)[-1], slot[1]])
    # a hidden-by-override instance must really be hidden (scale ~1e-4 at its slot)
    shown = []
    for iid, st in b.applied.items():
        slot = b.slot.get(iid)
        if st["deleted"] and slot:
            t = b.comps[slot[0]].get_instance_transform(slot[1], True)
            if max(abs(t.scale3d.x), abs(t.scale3d.y), abs(t.scale3d.z)) > 0.01:
                shown.append(iid)
    REPORT[n] = {"rev": b.rev, "checked": checked, "hidden": hidden, "worst_cm": round(worst, 4),
                 "bad_count": len(bad), "bad_override": [x for x in bad if x[2] == "override"][:50],
                 "bad_table_sample": [x for x in bad if x[2] == "table"][:5], "deleted_but_shown": shown,
                 "pending_meshes": sorted(getattr(b, "pending", {}) or {})}
    if REQUEST.get("full"):
        REPORT[n]["bad_ids"] = [x[0] for x in bad]
