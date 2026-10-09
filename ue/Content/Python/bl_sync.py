"""人偶之心 · Blender→UE 实时预览 2026-10-09: lk_session entry for bl_sync_core (state lives in the imported module).
REQUEST {"action": "attach", "placements": "/abs/<batch>_placements.json", "name": "<ct_placements name>", "dest": optional}
        {"action": "apply", "overrides": "/abs/<batch>_overrides.json"}
        {"action": "watch", "overrides": ["/abs/a_overrides.json", ...], "interval": 0.2}   (applies on every change)
        {"action": "unwatch"} | {"action": "reset", "name": "<name>"} | {"action": "status"}
        {"action": "detach", "name": optional}   (stop watching, reset, give the guarded level files their write permission back)
        {"action": "where", "name": "<name>", "inst": "<instance id>"}   (centre and yaw of one instance as UE shows it)
        {"action": "materials", "name": "<name>", "inst": ["<id>", ...]}   (mesh and per-slot material of instances)
        {"action": "fingerprint"}   (R2: lights, sky, fog, post, foliage, cameras and untouched materials, as one hash)
        {"action": "reload"}   (re-import bl_sync_core after an update: drops the state, attach + watch again)
        {"action": "frame", "inst": "<instance id>", "cam": "BLSYNC", "dist": 1.6}   (CineCamera CAM_<cam> looking at it)
        {"action": "frame", "cam": "BLSYNC", "remove": true}   (delete that temporary camera again)
REPORT: what the core returned."""
import importlib, math
import unreal
import bl_sync_core as core

REQ = globals().get("REQUEST", {}) or {}
act = REQ.get("action", "status")
if act == "reload":
    core.detach()
    REPORT = {"reloaded": importlib.reload(core).__file__}
elif act == "attach":
    REPORT = core.attach(REQ)
elif act == "apply":
    REPORT = core.apply_file(REQ["overrides"], REQ.get("name"))
elif act == "watch":
    p = REQ["overrides"]
    REPORT = core.watch(p if isinstance(p, list) else [p], REQ.get("interval", 0.2))
elif act == "unwatch":
    REPORT = core.unwatch()
elif act == "reset":
    REPORT = core.reset(REQ["name"])
elif act == "detach":
    REPORT = core.detach(REQ.get("name"))
elif act == "fingerprint":
    REPORT = core.fingerprint()
elif act == "materials":
    REPORT = core.materials(REQ["name"], REQ["inst"])
elif act == "where":
    REPORT = core.where(REQ["name"], REQ["inst"])
elif act == "frame" and REQ.get("remove"):            # remove the temporary camera this script made (test views only)
    EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    label = "CAM_" + REQ.get("cam", "BLSYNC")
    gone = [a for a in EAS.get_all_level_actors() if isinstance(a, unreal.CineCameraActor) and a.get_actor_label() == label]
    EAS.destroy_actors(gone)
    REPORT = {"removed": len(gone)}
elif act == "frame":
    b = next(iter(core.S["batches"].values()))
    key, idx = b.slot[REQ["inst"]]
    comp = b.comps[key]
    bb = comp.get_editor_property("static_mesh").get_bounds()
    t = comp.get_instance_transform(idx, True)
    c = t.transform_location(bb.origin)
    r = max(bb.box_extent.x, bb.box_extent.y, bb.box_extent.z) * float(REQ.get("dist", 1.6)) * 2.0
    yaw, pitch = float(REQ.get("yaw", 225.0)), float(REQ.get("pitch", -25.0))
    d = unreal.Vector(math.cos(math.radians(pitch)) * math.cos(math.radians(yaw)),
                      math.cos(math.radians(pitch)) * math.sin(math.radians(yaw)), math.sin(math.radians(pitch)))
    loc = c - d * r
    EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    label = "CAM_" + REQ.get("cam", "BLSYNC")
    cam = next((a for a in EAS.get_all_level_actors()
                if isinstance(a, unreal.CineCameraActor) and a.get_actor_label() == label), None)
    if cam is None:
        cam = EAS.spawn_actor_from_class(unreal.CineCameraActor, loc, unreal.Rotator(0, 0, 0))
        cam.set_actor_label(label)
    cam.set_actor_location_and_rotation(loc, unreal.Rotator(roll=0.0, pitch=pitch, yaw=yaw), False, True)
    cc = cam.get_cine_camera_component()
    cc.set_editor_property("current_focal_length", float(REQ.get("focal", 24.0)))
    fs = cc.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.DISABLE)
    cc.set_editor_property("focus_settings", fs)
    REPORT = {"cam": label, "center_m": [c.x / 100, -c.y / 100, c.z / 100], "dist_m": round(r / 100, 1)}
else:
    REPORT = {"batches": {k: {"rev": b.rev, "overrides": len(b.applied), "instances": len(b.base)}
                          for k, b in core.S["batches"].items()},
              "watch": (core.S["watch"] or {}).get("paths")}
