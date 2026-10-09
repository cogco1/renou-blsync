# SPDX-License-Identifier: GPL-3.0-or-later
"""No-UE package regression checks; run with Python 3.11+ or Blender's Python."""
import ast
import importlib.util
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_addon', ROOT / 'tools/build_addon.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ExtensionPackageTests(unittest.TestCase):
    def test_zip_contents_and_metadata(self):
        path = builder.build()
        with zipfile.ZipFile(path) as archive:
            expected = {p.name for p in (ROOT / 'blender/renou_blsync').glob('*.py')}
            expected |= {'blender_manifest.toml', 'renou_blsync_lib.py', 'LICENSE'}
            self.assertEqual(set(archive.namelist()), expected)
            self.assertIsNone(archive.testzip())
            metadata = tomllib.loads(archive.read('blender_manifest.toml').decode())
            self.assertEqual(metadata['id'], 'renou_blsync')
            self.assertEqual(metadata['license'], ['SPDX:GPL-3.0-or-later'])
            self.assertEqual(archive.read('LICENSE'), (ROOT / 'LICENSE').read_bytes())
            self.assertEqual(archive.read('renou_blsync_lib.py'),
                             (ROOT / 'blender/renou_blsync_lib.py').read_bytes())
            for name in expected:
                if name.endswith('.py'):
                    source = archive.read(name).decode()
                    self.assertIn('# SPDX-License-Identifier: GPL-3.0-or-later', source.splitlines()[:2])
                    ast.parse(source)

    def test_metadata_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(ROOT / 'blender', root / 'blender', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copy2(ROOT / 'LICENSE', root / 'LICENSE')
            manifest = root / 'blender/renou_blsync/blender_manifest.toml'
            original = manifest.read_text()
            for key, old, new in [('id', 'renou_blsync', 'wrong_id'),
                                  ('version', '0.1.0', '9.0.0'),
                                  ('blender_version_min', '5.2.0', '4.0.0')]:
                with self.subTest(key=key):
                    manifest.write_text(original.replace(f'{key} = "{old}"', f'{key} = "{new}"'))
                    with self.assertRaises(ValueError):
                        builder.build(root)
            manifest.write_text(original)
            (root / 'LICENSE').unlink()
            with self.assertRaises(FileNotFoundError):
                builder.build(root)

    def test_source_spdx(self):
        for folder in ['blender', 'tools', 'tests', 'ue', 'examples']:
            for path in (ROOT / folder).rglob('*.py'):
                with self.subTest(path=str(path.relative_to(ROOT))):
                    self.assertIn('# SPDX-License-Identifier: GPL-3.0-or-later', path.read_text().splitlines()[:2])


if __name__ == '__main__':
    unittest.main()
