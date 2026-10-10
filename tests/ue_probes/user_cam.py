"""test editor only: a camera that is not bl_sync's, with the label frame uses. REQUEST {"mode": "spawn" | "check" | "delete"}"""
import unreal

EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
cams = [a for a in EAS.get_all_level_actors() if isinstance(a, unreal.CineCameraActor) and a.get_actor_label() == "CAM_BLSYNC"]
mode = REQUEST.get("mode", "check")
if mode == "spawn":
    c = EAS.spawn_actor_from_class(unreal.CineCameraActor, unreal.Vector(123, 456, 789), unreal.Rotator(0, 0, 0))
    c.set_actor_label("CAM_BLSYNC")
    cams.append(c)
elif mode == "delete":
    EAS.destroy_actors(cams)
REPORT = {"cams": [{"tags": [str(t) for t in c.tags], "loc": [round(v, 1) for v in (c.get_actor_location().x,
          c.get_actor_location().y, c.get_actor_location().z)]} for c in cams] if mode != "delete" else len(cams)}
