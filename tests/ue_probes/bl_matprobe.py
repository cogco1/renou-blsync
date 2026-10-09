# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender→UE 实时预览 test only: simulate UE-owned materials and read them back.
REQUEST {"paint": "/Engine/BasicShapes/BasicShapeMaterial"} -> every HISM slot of every attached batch gets that override
        {"inst": ["id", ...]} -> per instance: mesh, per-slot material path"""
import unreal
import bl_sync_core as core
REQ = globals().get("REQUEST", {}) or {}
b = next(iter(core.S["batches"].values()))
REPORT = {}
if REQ.get("paint"):
    m = unreal.load_asset(REQ["paint"])
    n = 0
    for c in b.comps.values():
        for i in range(len(core.slot_names(c.get_editor_property("static_mesh")))):
            c.set_material(i, m)
            n += 1
    REPORT["painted_slots"] = n
for iid in REQ.get("inst", []):
    key, idx = b.slot[iid]
    c = b.comps[key]
    mesh = c.get_editor_property("static_mesh")
    REPORT[iid] = {"mesh": mesh.get_name(), "slots": {n: c.get_material(i).get_name() for i, n in enumerate(core.slot_names(mesh))}}
