"""Session state of the add-on (module globals: Batch objects cannot live in .blend data). Lost on reload, by design:
re-attach after opening a file."""
import bpy


def _import_lib():
    try:
        from . import renou_blsync_lib as lib          # inside the add-on zip made by tools/build_addon.py
    except ImportError:
        import renou_blsync_lib as lib                 # repo checkout: blender/ is on sys.path
    return lib


rb = _import_lib()

BATCHES = {}         # batch name -> rb.Batch
DIRTY = set()        # batch names with unpublished changes
GEO_DIRTY = {}       # batch name -> parts whose mesh may have changed (checked by signature before export)
RESULTS = {}         # batch name -> last delivery result, main-thread copy for the panel
LAST_SENT = {}       # batch name -> signature of the last document sent (skip identical live publishes)
BLOCKED = {}         # batch name -> why it is not published (its file could not be loaded back when attaching)
SNAPS = {}           # batch name -> (time read, newest snapshots) for the panel (the folder is read at most every 2 s)
LIVE = False
LAST_ERROR = ""
RECEIPT_WAIT = 5.0   # seconds the worker waits for UE's receipt before moving on
MESH_WAIT = 300.0    # then, if UE is still importing new meshes (#28), how long it waits for the complete receipt


def settings(context=None):
    return (context or bpy.context).scene.renou_sync


def interval():
    try:
        return max(0.05, float(settings().interval))
    except Exception:
        return 0.25


def batch_for(iid):
    for name, B in BATCHES.items():
        if B.batch_of(iid):
            return name
    return None


def snapshots(name, limit=8):
    import time
    t, rows = SNAPS.get(name, (0.0, []))
    if time.time() - t > 2.0 and name in BATCHES:
        try:
            rows = BATCHES[name].snapshots(limit)
        except Exception:
            rows = []
        SNAPS[name] = (time.time(), rows)
    return rows


def reset_all():
    global LIVE, LAST_ERROR
    BATCHES.clear()
    DIRTY.clear()
    GEO_DIRTY.clear()
    RESULTS.clear()
    LAST_SENT.clear()
    SNAPS.clear()
    BLOCKED.clear()
    LIVE = False
    LAST_ERROR = ""
