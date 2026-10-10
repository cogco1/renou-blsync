"""test editor only (Ash 10-10, #35): make a batch's finish_imports() fail, or stop failing.
REQUEST {"name": "<batch>", "mode": "on" | "off", "retry_s": 3}"""
import bl_sync_core as core

b = core.S["batches"][REQUEST["name"]]
core.FINISH_RETRY_S = float(REQUEST.get("retry_s", core.FINISH_RETRY_S))
if REQUEST.get("mode") == "on":
    if "finish_imports" not in vars(b):
        def broken():
            raise RuntimeError("injected finish failure (test)")
        b.finish_imports = broken
else:
    vars(b).pop("finish_imports", None)
REPORT = {"fault": "finish_imports" in vars(b), "retry_s": core.FINISH_RETRY_S, "pending": sorted(b.pending)}
