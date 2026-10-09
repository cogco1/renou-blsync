# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender→UE 实时预览 test only (R3): an L_S02-like structure (persistent level + the batch as a streamed sublevel),
a VFX-style edit + save while the preview is on, and the file times / modes of both levels.
REQUEST {"make_host": true} | {"vfx_save": 7.5}  (sun intensity to set on R3_Sun, then save_dirty_packages)"""
import os, time
from pathlib import Path
import unreal
REQ = globals().get("REQUEST", {}) or {}
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
UES = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
EAL = unreal.EditorAssetLibrary
C = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())) / "BlSync"
HOST, SUB = "/Game/BlSync/L_Host", "/Game/BlSync/L_Test"


def files():
    return {f.name: [time.strftime("%H:%M:%S", time.localtime(f.stat().st_mtime)), oct(f.stat().st_mode & 0o777)]
            for f in (C / "L_Host.umap", C / "L_Test.umap") if f.exists()}


REPORT = {}
if REQ.get("make_host"):
    if EAL.does_asset_exist(HOST):
        LES.load_level(HOST)
        REPORT["host"] = "loaded"
    else:
        LES.new_level(HOST)
        sun = EAS.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 1000), unreal.Rotator(0, -40, 0))
        sun.set_actor_label("R3_Sun")
        unreal.EditorLevelUtils.add_level_to_world(UES.get_editor_world(), SUB, unreal.LevelStreamingAlwaysLoaded)
        unreal.EditorLoadingAndSavingUtils.save_map(UES.get_editor_world(), HOST)
        REPORT["host"] = "created"
    REPORT["levels"] = [l.get_outer().get_path_name() for l in unreal.EditorLevelUtils.get_levels(UES.get_editor_world())]
    sun = next((a for a in EAS.get_all_level_actors() if a.get_actor_label() == "R3_Sun"), None)
    REPORT["sun_intensity"] = sun.get_component_by_class(unreal.DirectionalLightComponent).get_editor_property("intensity") if sun else None
if "vfx_save" in REQ:
    REPORT["before"] = files()
    sun = next(a for a in EAS.get_all_level_actors() if a.get_actor_label() == "R3_Sun")
    sun.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property("intensity", float(REQ["vfx_save"]))
    sun.modify()
    t = time.time()
    REPORT["save_dirty_packages"] = unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    REPORT["save_s"] = round(time.time() - t, 2)
    REPORT["after"] = files()
