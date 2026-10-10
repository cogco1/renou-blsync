"""test editor only: instance count over every HISM on the batch's host actors (catches a preview added twice)."""
import unreal
import bl_sync_core as core

REPORT = {}
for n, b in core.S["batches"].items():
    comps = [c for a in b.hosts.values() for c in a.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)]
    REPORT[n] = {"hism": len(comps), "instances": sum(c.get_instance_count() for c in comps)}
