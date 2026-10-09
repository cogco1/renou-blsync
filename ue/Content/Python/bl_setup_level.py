"""人偶之心 · Blender→UE 实时预览 test copy 2026-10-09: make the test level (new, empty) with sun, sky, fog.
REQUEST {"map": "/Game/BlSync/L_Test"}. Then ct_placements builds the batch into it (its "map" = the same path)."""
import unreal
REQ = globals().get("REQUEST", {}) or {}
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
UES = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
EAL = unreal.EditorAssetLibrary
m = REQ.get("map", "/Game/BlSync/L_Test")
if EAL.does_asset_exist(m):
    LES.load_level(m)
    REPORT = {"loaded": m}
else:
    LES.new_level(m)
    sun = EAS.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 50000),
                                     unreal.Rotator(roll=0.0, pitch=-35.0, yaw=225.0))
    lc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    lc.set_editor_property("intensity", 8.0)
    lc.set_editor_property("atmosphere_sun_light", True)
    EAS.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    sky = EAS.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    sky.get_component_by_class(unreal.SkyLightComponent).set_editor_property("real_time_capture", True)
    EAS.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    ppv = EAS.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    ppv.set_editor_property("unbound", True)
    unreal.EditorLoadingAndSavingUtils.save_map(UES.get_editor_world(), m)
    REPORT = {"created": m}
