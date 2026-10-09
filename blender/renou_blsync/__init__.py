# SPDX-License-Identifier: GPL-3.0-or-later
"""renou_blsync: Blender → UE live sync for 人偶之心 (LS01).

The add-on is a thin shell: a live switch, a change listener and a panel. Everything else - loading a batch, computing
the cumulative override document, exporting one part, writing back - lives in renou_blsync_lib, the same library the
engineering scripts use. See docs/ARCHITECTURE.md."""

bl_info = {
    "name": "Renou Sync (Blender → UE live)",
    "author": "人偶之心",
    "version": (0, 1, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Renou",
    "description": "Blender 管摆放和网格，UE 管材质灯光；改了自动发到 UE（参照 D5 LiveSync）",
    "category": "Import-Export",
}

from . import live, ops, props, ui   # noqa: E402

_MODULES = (props, ops, ui, live)


def register():
    for m in _MODULES:
        m.register()


def unregister():
    for m in reversed(_MODULES):
        m.unregister()
