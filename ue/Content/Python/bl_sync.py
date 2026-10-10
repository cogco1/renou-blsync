"""人偶之心 · Blender→UE 实时预览 2026-10-09: lk_session entry for bl_sync_core (state lives in the imported module).
REQUEST {"action": "attach", "placements": "/abs/<batch>_placements.json", "name": "<ct_placements name>", "dest": optional}
        {"action": "apply", "overrides": "/abs/<batch>_overrides.json"}
        {"action": "watch", "overrides": ["/abs/a_overrides.json", ...], "interval": 0.2}   (applies on every change)
        {"action": "unwatch"} | {"action": "reset", "name": "<name>"} | {"action": "status"}
        {"action": "detach", "name": optional}   (stop watching, reset, give the guarded level files their write permission back)
        {"action": "where", "name": "<name>", "inst": "<instance id>"}   (centre and yaw of one instance as UE shows it)
        {"action": "materials", "name": "<name>", "inst": ["<id>", ...]}   (mesh and per-slot material of instances)
        {"action": "attach", "kind": "veg", "placements": "/abs/veg_..._placements.json", "veg": "S02"}   (vegetation, #12)
        {"action": "suspend"} / {"action": "resume"}   (UE save: previews back to the tables, then re-applied)
        {"action": "remap", "name": optional}   (slots showing the placeholder get their material again from table / rules)
        {"action": "fingerprint"}   (R2: lights, sky, fog, post, foliage, cameras and untouched materials, as one hash)
        {"action": "reload"}   (re-import bl_sync_core after an update: drops the state, attach + watch again)
        {"action": "frame", "inst": "<instance id>", "cam": "BLSYNC", "dist": 1.6}   (CineCamera CAM_<cam> looking at it)
        {"action": "frame", "cam": "BLSYNC", "remove": true}   (delete that temporary camera again)
REPORT: what the core returned."""
import importlib, math
import unreal
import bl_sync_core as core

REQ = globals().get("REQUEST", {}) or {}
FRAME_TAG = "BLSYNC_FRAME_CAM"                        # cameras made by "frame" (the only ones it moves or removes)
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
elif act == "remap":                                 # after 视效 extends the slot table / rules: re-resolve placeholders
    REPORT = core.remap(REQ.get("name"))
elif act == "suspend":                               # before UE saves a level that holds previewed actors
    REPORT = core.suspend()
elif act == "resume":
    REPORT = core.resume()
elif act == "detach":
    REPORT = core.detach(REQ.get("name"))
elif act == "import_probe":                          # issue #11: time one import into /Game/_LivePreview/_probe, change nothing
    import time
    t = time.time()
    folder = f"{core.LIVE_ROOT}/_probe/{REQ.get('tag', 'p')}_{int(t)}"
    # self-contained (runpy reloads this file on every request; the cached core module stays as it is)
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    params.set_editor_property("replace_existing", True)
    pipe = unreal.SystemLibrary.duplicate_object(
        unreal.load_object(None, "/Interchange/Pipelines/DefaultGLTFAssetsPipeline.DefaultGLTFAssetsPipeline"), mgr)
    mp = pipe.get_editor_property("mesh_pipeline")
    opts = [("build_nanite", True), ("generate_lightmap_u_vs", False), ("collision", not REQ.get("preview", True))]
    if REQ.get("preview", True):
        opts.append(("distance_field_resolution_scale", 0.0))
    for k, v in opts:
        mp.set_editor_property(k, v)
    skipped = []
    if not REQ.get("materials", True):                # issue #11: no GLB materials / textures (UE assigns its own per slot)
        for sub, k in (("material_pipeline", "import_materials"), ("texture_pipeline", "import_textures")):
            try:
                pipe.get_editor_property(sub).set_editor_property(k, False)
                skipped.append(f"{sub}.{k}")
            except Exception as exc:
                skipped.append(f"{sub}.{k}: {exc}")
    params.set_editor_property("override_pipelines", [
        unreal.SoftObjectPath(pipe.get_path_name()),
        unreal.SoftObjectPath("/Interchange/Pipelines/DefaultGLTFPipeline.DefaultGLTFPipeline")])
    ok = mgr.import_asset(folder, mgr.create_source_data(str(REQ["glb"])), params)
    sms = unreal.EditorAssetLibrary.list_assets(folder, recursive=True, include_folder=False)
    m = next((unreal.load_asset(x) for x in sms if isinstance(unreal.load_asset(x), unreal.StaticMesh)), None)
    REPORT = {"ok": bool(ok), "seconds": round(time.time() - t, 2), "folder": folder, "preview": bool(REQ.get("preview", True)),
              "skipped": skipped, "assets": len(sms), "slots": core.slot_names(m) if m else None}
elif act == "hosts":                                 # read-only: actors whose tags start with a prefix, their level and HISMs
    EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    pre = REQ.get("prefix", "VEG_")
    rows = []
    for a in EAS.get_all_level_actors():
        tags = [str(t) for t in a.tags]
        if not any(t.startswith(pre) for t in tags):
            continue
        comps = a.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        rows.append({"label": a.get_actor_label(), "level": a.get_outer().get_outer().get_path_name().split(".")[0],
                     "tags": tags, "hism": len(comps), "instances": sum(c.get_instance_count() for c in comps),
                     "meshes": sorted({c.get_editor_property("static_mesh").get_name() for c in comps if c.get_editor_property("static_mesh")})})
    REPORT = {"prefix": pre, "actors": rows}
elif act == "fingerprint":
    REPORT = core.fingerprint()
elif act == "materials":
    REPORT = core.materials(REQ["name"], REQ["inst"])
elif act == "where":
    REPORT = core.where(REQ["name"], REQ["inst"])
elif act == "frame" and REQ.get("remove"):            # remove the temporary camera this script made (test views only)
    # only cameras frame made (tag BLSYNC_FRAME_CAM): Ash 10-10, a camera of 视效's with the same label must stay
    EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    label = "CAM_" + REQ.get("cam", "BLSYNC")
    gone = [a for a in EAS.get_all_level_actors() if isinstance(a, unreal.CineCameraActor) and a.get_actor_label() == label
            and FRAME_TAG in [str(t) for t in a.tags]]
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
    cam = next((a for a in EAS.get_all_level_actors() if isinstance(a, unreal.CineCameraActor)
                and a.get_actor_label() == label and FRAME_TAG in [str(t) for t in a.tags]), None)
    if cam is None:                                    # never moves a camera this script did not make
        cam = EAS.spawn_actor_from_class(unreal.CineCameraActor, loc, unreal.Rotator(0, 0, 0))
        cam.set_actor_label(label)
        cam.set_editor_property("tags", [unreal.Name(FRAME_TAG)])
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
