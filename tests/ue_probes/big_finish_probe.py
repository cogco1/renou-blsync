"""test editor only (#28 follow-up): which step after an asynchronous import of a very large mesh holds the game thread?
REQUEST {"mode": "start", "glb": path, "folder": "/Game/BlSyncProbe/x"} | {"mode": "result"}
After the import callback, one step per tick, each timed: load_asset, get_num_triangles, a HISM set_static_mesh."""
import builtins, time
import unreal
import bl_sync_core as core

P = getattr(builtins, "_BIGP", None)
if P is None:
    P = builtins._BIGP = {"h": None}


def _tick(dt):
    now = time.monotonic()
    if P.get("last") is not None:
        P["max_gap"] = max(P["max_gap"], now - P["last"])
        if now - P["last"] > 0.5:
            P["gaps"].append([round(P["last"] - P["t0"], 1), round(now - P["last"], 2)])
    P["last"] = now
    st = P.get("stage")
    if st == "imported":
        t = time.monotonic()
        paths = core.EAL.list_assets(P["folder"], recursive=True, include_folder=False)
        P["sm"] = next((a for a in (unreal.load_asset(p) for p in paths) if isinstance(a, unreal.StaticMesh)), None)
        P["steps"]["load_asset_s"] = round(time.monotonic() - t, 2)
        P["stage"] = "loaded"
    elif st == "loaded":
        sm = P["sm"]
        P["steps"]["compiling_flags"] = [n for n in dir(sm) if "compil" in n.lower()]
        t = time.monotonic()
        P["steps"]["triangles"] = sm.get_num_triangles(0)
        P["steps"]["get_num_triangles_s"] = round(time.monotonic() - t, 2)
        P["stage"] = "counted"
    elif st == "counted":
        t = time.monotonic()
        a = core.EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, -50000), unreal.Rotator(0, 0, 0))
        sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
        BL = unreal.SubobjectDataBlueprintFunctionLibrary
        root = sub.k2_gather_subobject_data_for_instance(a)[0]
        h, _ = sub.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=root,
                                     new_class=unreal.HierarchicalInstancedStaticMeshComponent, blueprint_context=None))
        c = BL.get_object(BL.get_data(h))
        c.set_static_mesh(P["sm"])
        c.add_instance(unreal.Transform(), True)
        P["steps"]["hism_set_static_mesh_s"] = round(time.monotonic() - t, 2)
        P["actor"] = a
        P["stage"] = "done"
        P["done_after_s"] = round(time.monotonic() - P["t0"], 1)


if P["h"] is None:
    P["h"] = unreal.register_slate_post_tick_callback(_tick)

if REQUEST.get("mode") == "start":
    P.update(t0=time.monotonic(), last=None, max_gap=0.0, gaps=[], steps={}, stage="importing", folder=REQUEST["folder"])

    def done(objs):
        P["steps"]["callback_after_s"] = round(time.monotonic() - P["t0"], 1)
        P["stage"] = "imported"
    t = time.monotonic()
    core.interchange_mesh(REQUEST["glb"], REQUEST["folder"], materials=False, on_done=done)
    P["steps"]["start_call_s"] = round(time.monotonic() - t, 2)
    REPORT = {"started": P["steps"]}
else:
    REPORT = {k: P.get(k) for k in ("stage", "steps", "max_gap", "gaps", "done_after_s")}
    if P.get("stage") == "done" and P.get("actor"):
        P["actor"].destroy_actor()
        P["actor"] = None
