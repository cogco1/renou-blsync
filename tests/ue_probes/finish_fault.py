"""test editor only (Ash 10-10, #35): make a batch's finish fail, or stop failing.
REQUEST {"name": "<batch>", "mode": "on" | "mesh_on" | "apply_on" | "off", "retry_s": 3}
on: finish_imports() raises before anything (the first fault); mesh_on: finish_mesh() raises (inside finish_imports,
after the part was picked); apply_on: the apply() inside finish_imports raises (after the meshes are in); other applies work."""
import bl_sync_core as core

b = core.S["batches"][REQUEST["name"]]
core.FINISH_RETRY_S = float(REQUEST.get("retry_s", core.FINISH_RETRY_S))
mode = REQUEST.get("mode")
for attr in ("finish_imports", "finish_mesh", "apply"):
    vars(b).pop(attr, None)
if mode in ("on", "mesh_on", "apply_on"):
    attr = {"on": "finish_imports", "mesh_on": "finish_mesh", "apply_on": "apply"}[mode]

    real = getattr(type(b), attr)

    def broken(*a, **k):
        import inspect
        if attr == "apply" and "finish_imports" not in [f.function for f in inspect.stack()[1:4]]:
            return real(b, *a, **k)                     # only the re-apply inside finish_imports fails
        raise RuntimeError(f"injected {attr} failure (test)")
    setattr(b, attr, broken)
REPORT = {"fault": [a for a in ("finish_imports", "finish_mesh", "apply") if a in vars(b)], "retry_s": core.FINISH_RETRY_S,
          "pending": sorted(b.pending), "reapply_due": getattr(b, "reapply_due", False)}
