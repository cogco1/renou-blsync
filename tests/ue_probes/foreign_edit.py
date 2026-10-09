"""test editor only: change one instance of an attached batch the way another tool would (视效's lk_ns_hide).
REQUEST {"name": "<batch>", "inst": "<id>", "mode": "sink" | "show"}
sink = 10 km down at scale 0.001 (lk_ns_hide); show = the table transform at scale 1 (a restore that brings back an
instance the override deletes)."""
import unreal
import bl_sync_core as core

b = core.S["batches"][REQUEST["name"]]
key, idx = b.slot[REQUEST["inst"]]
c = b.comps[key]
t = c.get_instance_transform(idx, True)
if REQUEST["mode"] == "sink":
    t2 = unreal.Transform(t.translation - unreal.Vector(0, 0, 1.0e6), t.rotation.rotator(), unreal.Vector(0.001, 0.001, 0.001))
else:
    t2 = core.ue_xf(b.base[REQUEST["inst"]])
c.update_instance_transform(idx, t2, True, True, True)
REPORT = {"inst": REQUEST["inst"], "mode": REQUEST["mode"], "z_cm": round(t2.translation.z, 1),
          "scale": round(t2.scale3d.x, 4)}
