"""test editor only: core.record_name() for a record without "name" (vegetation)."""
import bl_sync_core as core
REPORT = {"veg_without_name": core.record_name({"kind": "veg", "placements": REQUEST["placements"]}),
          "named": core.record_name({"name": "A0403", "placements": REQUEST["placements"]})}
