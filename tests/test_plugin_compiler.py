"""Unit tests for .pywer plugin packaging, AST validation, and compilation."""

import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from pywer.plugin.compiler import PluginCompileError, PluginCompiler


class TestPluginCompiler(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="pywer_test_plugin_")
        self.source_dir = Path(self.temp_dir) / "source"
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = Path(self.temp_dir) / "dist"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pack_valid_plugin(self):
        manifest_data = {
            "name": "SamplePlugin",
            "version": "1.0.0",
            "main": "main:SamplePlugin",
            "api_version": "1.0.0",
            "author": "PywerTeam",
            "description": "A compiled test plugin",
        }
        with open(self.source_dir / "plugin.json", "w", encoding="utf-8") as f:
            json.dump(manifest_data, f)

        with open(self.source_dir / "main.py", "w", encoding="utf-8") as f:
            f.write("class SamplePlugin:\n    pass\n")

        utils_dir = self.source_dir / "utils"
        utils_dir.mkdir()
        with open(utils_dir / "helpers.py", "w", encoding="utf-8") as f:
            f.write("def helper():\n    return 42\n")

        output_path = self.output_dir / "SamplePlugin.pywer"
        compiled_file = PluginCompiler.pack(self.source_dir, output_path)

        self.assertTrue(compiled_file.exists())
        self.assertEqual(compiled_file.suffix, ".pywer")

        # Verify zip archive contents
        with zipfile.ZipFile(compiled_file, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("plugin.json", namelist)
            self.assertIn("main.py", namelist)
            # Check normalized forward-slash archive paths
            self.assertTrue(
                "utils/helpers.py" in namelist or "utils\\helpers.py" in namelist
            )

        # Inspect manifest without extraction
        manifest = PluginCompiler.inspect(compiled_file)
        self.assertEqual(manifest["name"], "SamplePlugin")
        self.assertEqual(manifest["version"], "1.0.0")

    def test_syntax_error_detection(self):
        manifest_data = {
            "name": "BrokenPlugin",
            "version": "1.0.0",
            "main": "main:Broken",
            "api_version": "1.0.0",
        }
        with open(self.source_dir / "plugin.json", "w", encoding="utf-8") as f:
            json.dump(manifest_data, f)

        # Invalid Python syntax
        with open(self.source_dir / "main.py", "w", encoding="utf-8") as f:
            f.write("def broken(\n")

        output_path = self.output_dir / "BrokenPlugin.pywer"
        with self.assertRaises(PluginCompileError) as ctx:
            PluginCompiler.pack(self.source_dir, output_path)

        self.assertIn("Syntax error", str(ctx.exception))
        self.assertIn("main.py", str(ctx.exception))

    def test_missing_manifest(self):
        with open(self.source_dir / "main.py", "w", encoding="utf-8") as f:
            f.write("x = 1\n")

        output_path = self.output_dir / "NoManifest.pywer"
        with self.assertRaises(PluginCompileError) as ctx:
            PluginCompiler.pack(self.source_dir, output_path)

        self.assertIn("plugin.json", str(ctx.exception))

    def test_invalid_manifest_fields(self):
        manifest_data = {
            "name": "MissingMain",
            "version": "1.0.0",
            # Missing "main" and "api_version"
        }
        with open(self.source_dir / "plugin.json", "w", encoding="utf-8") as f:
            json.dump(manifest_data, f)

        output_path = self.output_dir / "InvalidManifest.pywer"
        with self.assertRaises(PluginCompileError) as ctx:
            PluginCompiler.pack(self.source_dir, output_path)

        self.assertIn("main", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
