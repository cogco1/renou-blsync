# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke-test ZIP imports under the extension namespace, without installing or UE."""
import bpy
import importlib.util
from pathlib import Path
import sys
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
archive = next((root / 'build').glob('renou_blsync-*.zip'))
with tempfile.TemporaryDirectory() as temp:
    package = Path(temp) / 'renou_blsync'
    with zipfile.ZipFile(archive) as contents:
        contents.extractall(package)
    # Blender owns bl_ext; load our package under the same qualified naming pattern.
    name = 'bl_ext.test_repo.renou_blsync'
    spec = importlib.util.spec_from_file_location(name, package / '__init__.py',
                                                  submodule_search_locations=[str(package)])
    addon = importlib.util.module_from_spec(spec)
    sys.modules[name] = addon
    spec.loader.exec_module(addon)
    addon.register()
    assert hasattr(bpy.context.scene, 'renou_sync')
    assert addon.state.rb.__name__ == name + '.renou_blsync_lib'
    addon.unregister()
    assert not hasattr(bpy.types.Scene, 'renou_sync')
    addon.register()
    addon.unregister()
    print('PACKAGED EXTENSION REGISTER/UNREGISTER RESULT OK')
