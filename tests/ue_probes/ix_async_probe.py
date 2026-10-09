"""#28 probe (test editor only): how long does one big-mesh import hold the game thread, sync vs async Interchange?
REQUEST {"mode": "sync"|"async", "glb": path, "folder": "/Game/BlSyncProbe/x"} starts one import;
{"mode": "result"} returns what the tick recorder saw (gaps between slate ticks, call time, time to done)."""
import builtins, json, time
import unreal

P = getattr(builtins, "_IXP", None)
if P is None:
    P = builtins._IXP = {"runs": [], "cur": None, "last": None, "h": None}


def _tick(dt):
    now = time.monotonic()
    cur = P["cur"]
    if cur is not None:
        if P["last"] is not None:
            g = now - P["last"]
            cur["max_gap"] = max(cur["max_gap"], g)
            if g > 0.2:
                cur["gaps"].append(round(g, 2))
        cur["ticks"] += 1
        EAL = unreal.EditorAssetLibrary
        if cur.get("done_t") is None and EAL.does_directory_exist(cur["folder"]):
            sms = [p for p in EAL.list_assets(cur["folder"], recursive=True, include_folder=False)]
            if sms and (cur["mode"] == "sync" or cur.get("cb")):
                cur["done_t"] = round(now - cur["t0"], 2)
                cur["assets"] = sms[:4]
        if cur.get("done_t") is not None and now - cur["t0"] > cur["done_t"] + 3.0:
            P["runs"].append(cur)                  # 3 s more of ticks after done (late compilation hitches)
            P["cur"] = None
    P["last"] = now


if P["h"] is None:
    P["h"] = unreal.register_slate_post_tick_callback(_tick)

mode = REQUEST.get("mode", "result")
if mode == "result":
    REPORT = {"runs": P["runs"], "cur": P["cur"]}
else:
    import bl_sync_core as core
    glb, folder = REQUEST["glb"], REQUEST["folder"]
    cur = {"mode": mode, "glb": glb.rsplit("/", 1)[-1], "folder": folder, "max_gap": 0.0, "gaps": [], "ticks": 0,
           "t0": time.monotonic()}
    if mode == "sync":
        t = time.monotonic()
        core.interchange_mesh(glb, folder, materials=False)
        cur["call_s"] = round(time.monotonic() - t, 2)
        cur["pumped_ticks_in_call"] = cur["ticks"]
    else:
        mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
        params = unreal.ImportAssetParameters()
        params.set_editor_property("is_automated", True)
        params.set_editor_property("replace_existing", True)
        base = "DefaultGLTFAssetsPipeline"
        pipe = unreal.SystemLibrary.duplicate_object(unreal.load_object(None, f"/Interchange/Pipelines/{base}.{base}"), mgr)
        mp = pipe.get_editor_property("mesh_pipeline")
        for k, v in [("build_nanite", True), ("generate_lightmap_u_vs", False), ("collision", False),
                     ("distance_field_resolution_scale", 0.0)]:
            mp.set_editor_property(k, v)
        pipe.get_editor_property("material_pipeline").set_editor_property("import_materials", False)
        params.set_editor_property("override_pipelines", [
            unreal.SoftObjectPath(pipe.get_path_name()),
            unreal.SoftObjectPath("/Interchange/Pipelines/DefaultGLTFPipeline.DefaultGLTFPipeline")])

        def _done(objs):
            cur["cb"] = round(time.monotonic() - cur["t0"], 2)
            cur["cb_objs"] = [o.get_path_name() for o in objs][:4] if objs else []
        d = params.get_editor_property("on_assets_import_done")
        try:
            d.bind_callable(_done)
            cur["delegate"] = "bind"
        except Exception as e:
            try:
                d.add_callable(_done)
                cur["delegate"] = "add"
            except Exception as e2:
                cur["delegate"] = f"none: {e} / {e2}"
        params.set_editor_property("on_assets_import_done", d)
        P["keep"] = (params, pipe, _done)           # keep everything alive until done
        t = time.monotonic()
        ret = mgr.scripted_import_asset_async(folder, mgr.create_source_data(glb), params)
        cur["call_s"] = round(time.monotonic() - t, 2)
        cur["ret"] = repr(ret)[:200]
    P["cur"] = cur
    P["last"] = time.monotonic()
    REPORT = {"started": cur}
