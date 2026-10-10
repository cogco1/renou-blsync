"""The live switch (D5 LiveSync's start/stop): changes made by scripts or by hand are published automatically.

- depsgraph handler: only marks batches dirty (cheap, runs on every update)
- timer (main thread, every `interval` s): fixes Shift+D ids, exports parts whose mesh really changed, builds the
  cumulative override document
- one worker thread: writes / pushes it and waits for UE's receipt; the newest document per batch wins, so a slow
  ssh push never queues up stale states and never freezes the UI
"""
import json
import threading
import time
import traceback

import bpy

from . import state


@bpy.app.handlers.persistent
def on_depsgraph(scene, depsgraph):
    if not state.LIVE or not state.BATCHES:
        return
    if depsgraph.id_type_updated("COLLECTION"):          # objects linked / unlinked / deleted
        state.DIRTY.update(state.BATCHES)
    for u in depsgraph.updates:
        idb = getattr(u.id, "original", u.id)
        if not isinstance(idb, bpy.types.Object):
            continue
        iid = idb.get("blsync_id")
        name = state.batch_for(iid) if iid else None
        if not name:
            continue
        state.DIRTY.add(name)
        if u.is_updated_geometry and idb.type == "MESH" and idb.get("blsync_part"):
            state.GEO_DIRTY.setdefault(name, set()).add(idb["blsync_part"])


class Worker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="renou_blsync worker")
        self.cv = threading.Condition()
        self.pending = {}            # batch name -> (Batch, override document): newest only
        self.results = {}            # batch name -> result dict, picked up by the timer
        self.stopped = False
        self.busy = False

    def submit(self, name, B, ov):
        with self.cv:
            self.pending[name] = (B, ov)
            self.cv.notify()

    def stop(self):
        with self.cv:
            self.stopped = True
            self.cv.notify()

    def take_results(self):
        with self.cv:
            r, self.results = self.results, {}
        return r

    def idle(self):
        with self.cv:
            return not self.pending and not self.busy

    def run(self):
        while True:
            with self.cv:
                while not self.pending and not self.stopped:
                    self.cv.wait(0.5)
                if self.stopped:
                    return
                name, (B, ov) = self.pending.popitem()
                self.busy = True
            t0 = time.time()
            try:
                res = B.deliver(ov)
                res["ue"] = self._wait(name, B, ov)
                if res["ue"] and res["ue"].get("complete") is False:
                    # #28: positions are in, new meshes still importing in UE: show that, then wait for the rest
                    self._post(name, dict(res), ov, t0)
                    res["ue"] = self._wait(name, B, ov, complete=True, limit=state.MESH_WAIT) or res["ue"]
            except Exception as e:                      # e.g. ssh failed: shown in the panel, the next change retries
                res = {"rev": ov["rev"], "overrides": len(ov["instances"]), "ue": None, "error": f"{type(e).__name__}: {e}"}
            res.update(label=ov.get("label", ""), seconds=round(time.time() - t0, 3), t=time.time())
            with self.cv:
                self.results[name] = res
                self.busy = False

    def _post(self, name, res, ov, t0):
        res.update(label=ov.get("label", ""), seconds=round(time.time() - t0, 3), t=time.time())
        with self.cv:
            self.results[name] = res

    def _wait(self, name, B, ov, complete=False, limit=None):
        t0 = time.time()
        while time.time() - t0 < (limit or state.RECEIPT_WAIT):
            st = B.wait_receipt(ov, wait=0.25, complete=complete)
            if st:
                return st
            with self.cv:
                if name in self.pending or self.stopped:   # a newer document is queued: stop waiting for this one
                    return None
        return None


WORKER = None


def worker():
    global WORKER
    if WORKER is None or not WORKER.is_alive():
        WORKER = Worker()
        WORKER.start()
    return WORKER


def collect_results():
    if WORKER is None:
        return
    got = WORKER.take_results()
    if got:
        state.RESULTS.update(got)
        _redraw()


def _redraw():
    wm = getattr(bpy.context, "window_manager", None)
    for win in (wm.windows if wm else []):
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def flush(label="live"):
    """publish every dirty batch now (main thread). Returns the batch names submitted."""
    sent = []
    for name in list(state.DIRTY):
        B = state.BATCHES.get(name)
        if name in state.BLOCKED:                        # Ash 10-10: never publish a batch whose file did not load back
            continue
        state.DIRTY.discard(name)
        if B is None:
            continue
        B.fix_duplicates()
        geo = state.GEO_DIRTY.get(name)
        if geo and bpy.context.mode == "OBJECT":         # edit-mode changes reach the mesh only when leaving edit mode
            for part in sorted(geo):
                B.export_part_if_changed(part)
            geo.clear()
        ov = B.build(label)
        sig = json.dumps([ov["instances"], ov["meshes"]], sort_keys=True)
        if label == "live" and state.LAST_SENT.get(name) == sig:
            B.rev -= 1                                   # nothing new (e.g. only a rename): keep the revision
            continue
        state.LAST_SENT[name] = sig
        worker().submit(name, B, ov)
        sent.append(name)
    return sent


def tick():
    """bpy.app.timers callback; also called directly by tests and by the 'publish now' operator."""
    if not state.LIVE:
        collect_results()
        return None                                      # unregisters the timer
    try:
        collect_results()
        flush("live")
    except Exception:
        state.LAST_ERROR = traceback.format_exc(limit=4)
    return state.interval()


def set_live(on):
    state.LIVE = bool(on)
    if on:
        worker()
        state.DIRTY.update(state.BATCHES)                # D5-style: switching on catches up with everything at once
        if not bpy.app.timers.is_registered(tick):
            bpy.app.timers.register(tick, first_interval=state.interval(), persistent=True)
    elif bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)


@bpy.app.handlers.persistent
def on_load(_dummy):
    """a new .blend: the Batch objects point at data that no longer exists."""
    set_live(False)
    state.reset_all()


def register():
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph)
    bpy.app.handlers.load_post.append(on_load)


def unregister():
    global WORKER
    set_live(False)
    for h, f in ((bpy.app.handlers.depsgraph_update_post, on_depsgraph), (bpy.app.handlers.load_post, on_load)):
        if f in h:
            h.remove(f)
    if WORKER is not None:
        WORKER.stop()
        WORKER = None
    state.reset_all()
