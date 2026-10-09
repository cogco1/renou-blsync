#!/usr/bin/env python3
"""Build the installable add-on zip: blender/renou_blsync/*.py plus the one shared library blender/renou_blsync_lib.py,
copied inside the package so the zip is self-contained (the repo keeps a single copy of the library).
    python3 tools/build_addon.py            -> build/renou_blsync-<version>.zip
Install in Blender: Edit > Preferences > Add-ons > Install from Disk."""
import ast, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
pkg = ROOT / "blender" / "renou_blsync"
init = (pkg / "__init__.py").read_text(encoding="utf-8")
info = ast.literal_eval(init.split("bl_info = ", 1)[1].split("\n}\n", 1)[0] + "\n}")
ver = ".".join(map(str, info["version"]))
out = ROOT / "build" / f"renou_blsync-{ver}.zip"
out.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(pkg.glob("*.py")):
        z.write(f, f"renou_blsync/{f.name}")
    z.write(ROOT / "blender" / "renou_blsync_lib.py", "renou_blsync/renou_blsync_lib.py")
print(out)
sys.exit(0)
