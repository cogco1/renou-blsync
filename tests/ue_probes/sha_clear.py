"""test editor only: forget every remembered GLB SHA-256 (to compare a resume with and without the cache)."""
import bl_sync_core as core
n = len(core._SHA)
core._SHA.clear()
REPORT = {"forgotten": n}
