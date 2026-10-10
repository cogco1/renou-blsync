"""test editor only: profile one apply_file. REQUEST {"name": "<batch>", "overrides": "/abs/file.json", "top": 25}
REPORT: wall seconds, receipt counts, the top functions by own time and by cumulative time."""
import cProfile, io, pstats, time
import bl_sync_core as core

pr = cProfile.Profile()
t = time.time()
pr.enable()
out = core.apply_file(REQUEST["overrides"], REQUEST.get("name"))
pr.disable()
wall = time.time() - t
REPORT = {"wall_s": round(wall, 2), "counts": out.get("counts"), "conflicts": len(out.get("conflicts") or [])}
for key in ("tottime", "cumulative"):
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats(key).print_stats(REQUEST.get("top", 18))
    lines = [l for l in s.getvalue().splitlines() if l.strip() and ("{" in l or ".py:" in l)]
    REPORT[key] = [l[:170] for l in lines[:REQUEST.get("top", 18)]]
