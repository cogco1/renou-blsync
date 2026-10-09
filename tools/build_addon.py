#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a self-contained Blender extension ZIP (manifest and entry point at root).

The repository keeps one shared library; the ZIP includes a copy beside __init__.py.
    python3 tools/build_addon.py -> build/renou_blsync-<version>.zip
"""
import ast
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def build(root=ROOT):
    root = Path(root)
    pkg = root / "blender" / "renou_blsync"
    tree = ast.parse((pkg / "__init__.py").read_text(encoding="utf-8"))
    info = next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "bl_info" for t in node.targets))
    manifest_path = pkg / "blender_manifest.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    version = ".".join(map(str, info["version"]))
    expected = {"id": pkg.name, "version": version, "name": info["name"],
                "blender_version_min": ".".join(map(str, info["blender"])),
                "license": ["SPDX:GPL-3.0-or-later"]}
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"manifest {key} must match {value!r}")
    license_path = root / "LICENSE"
    if not license_path.is_file():
        raise FileNotFoundError("LICENSE must be included in the extension")
    out = root / "build" / f"renou_blsync-{version}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Allowlist only source files, the manifest and license, never build/test data.
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(pkg.glob("*.py")):
            archive.write(file, file.name)
        archive.write(root / "blender" / "renou_blsync_lib.py", "renou_blsync_lib.py")
        archive.write(manifest_path, "blender_manifest.toml")
        archive.write(license_path, "LICENSE")
    return out


if __name__ == "__main__":
    print(build())
