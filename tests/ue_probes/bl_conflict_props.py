"""Blender→UE 实时预览 test only (#16): put two hand-placed props (plain StaticMeshActors, no sync tags) near CBD block
001, one where the block will be moved to and one far away. REQUEST {"remove": true} removes them again."""
import unreal
REQ = globals().get("REQUEST", {}) or {}
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
old = [a for a in EAS.get_all_level_actors() if a.get_actor_label().startswith("HANDPROP_TEST")]
EAS.destroy_actors(old)
REPORT = {"removed": len(old)}
if not REQ.get("remove"):
    cube = unreal.load_asset("/Engine/BasicShapes/Cube")
    for label, (x, y, z) in (("HANDPROP_TEST_hit", (591.7, -236.7, 120.0)), ("HANDPROP_TEST_far", (300.0, 400.0, 10.0))):
        a = EAS.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(x * 100, -y * 100, z * 100), unreal.Rotator(0, 0, 0))
        a.set_actor_label(label)
        a.static_mesh_component.set_static_mesh(cube)
        a.set_actor_scale3d(unreal.Vector(5, 5, 5))
    REPORT["spawned"] = 2
