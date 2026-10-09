"""#28 test (test editor only): record the gaps between editor ticks. REQUEST {"mode": "start" | "result"}."""
import builtins, time
import unreal

G = getattr(builtins, "_GAPREC", None)
if G is None:
    G = builtins._GAPREC = {"h": None}


def _tick(dt):
    now = time.monotonic()
    if G.get("last") is not None:
        g = now - G["last"]
        G["max"] = max(G["max"], g)
        G["ticks"] += 1
        if g > 0.25:
            G["gaps"].append([round(G["last"] - G["t0"], 2), round(g, 2)])
    G["last"] = now


if REQUEST.get("mode") == "start":
    G.update(t0=time.monotonic(), last=None, max=0.0, ticks=0, gaps=[])
    if G["h"] is None:
        G["h"] = unreal.register_slate_post_tick_callback(_tick)
    REPORT = {"started": True}
else:
    REPORT = {"seconds": round(time.monotonic() - G["t0"], 1), "ticks": G["ticks"], "max_gap_s": round(G["max"], 2),
              "gaps_over_0.25s [at_s, gap_s]": G["gaps"][:40]}
    if REQUEST.get("mode") == "stop" and G["h"] is not None:
        unreal.unregister_slate_post_tick_callback(G["h"])
        G["h"] = None
