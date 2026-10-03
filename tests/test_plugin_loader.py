"""Unit tests for virtual in-memory .pywer plugin loader and PluginBase."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from pywer.plugin.base import PluginBase, PluginConfig, PluginManifest
from pywer.plugin.compiler import PluginCompiler
from pywer.plugin.loader import VirtualPluginLoader


class MockServer:
    def __init__(self):
        self.event_manager = None
        self.command_manager = None


class TestPluginLoader(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="pywer_test_loader_")
        self.source_dir = Path(self.temp_dir) / "source"
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.dist_dir = Path(self.temp_dir) / "dist"
        self.dist_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = Path(self.temp_dir) / "plugin_data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.server = MockServer()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _build_test_plugin(self) -> Path:
        manifest = {
            "name": "VirtualDemo",
            "version": "1.2.3",
            "main": "main:VirtualPlugin",
            "api_version": "1.0.0",
            "author": "Antigravity",
            "description": "Virtual loader test plugin",
        }
        with open(self.source_dir / "plugin.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        # Subpackage with helper
        utils_dir = self.source_dir / "utils"
        utils_dir.mkdir()
        with open(utils_dir / "__init__.py", "w", encoding="utf-8") as f:
            f.write("# utils package\n")
        with open(utils_dir / "maths.py", "w", encoding="utf-8") as f:
            f.write("def add_ten(n):\n    return n + 10\n")

        # Bundled asset
        assets_dir = self.source_dir / "assets"
        assets_dir.mkdir()
        with open(assets_dir / "motd.txt", "w", encoding="utf-8") as f:
            f.write("Welcome to Virtual Pywer!")

        # Main plugin script
        main_content = """from pywer.plugin.base import PluginBase
from .utils.maths import add_ten

class VirtualPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.load_called = False
        self.enable_called = False
        self.disable_called = False

    def on_load(self):
        self.load_called = True

    def on_enable(self):
        self.enable_called = True

    def on_disable(self):
        self.disable_called = True

    def calculate(self, val):
        return add_ten(val)
"""
        with open(self.source_dir / "main.py", "w", encoding="utf-8") as f:
            f.write(main_content)

        pkg_path = self.dist_dir / "VirtualDemo.pywer"
        return PluginCompiler.pack(self.source_dir, pkg_path)

    def test_virtual_loading_and_submodules(self):
        pkg_path = self._build_test_plugin()
        self.assertTrue(pkg_path.exists())

        plugin = VirtualPluginLoader.load_plugin(pkg_path, self.server, self.data_dir)

        # Check instance properties
        self.assertIsInstance(plugin, PluginBase)
        self.assertEqual(plugin.name, "VirtualDemo")
        self.assertEqual(plugin.version, "1.2.3")
        self.assertTrue(plugin.load_called)

        # Test in-memory submodule execution
        calc_result = plugin.calculate(25)
        self.assertEqual(calc_result, 35)

        # Test bundled resource reading without extraction
        motd_bytes = plugin.get_resource("assets/motd.txt")
        self.assertIsNotNone(motd_bytes)
        self.assertEqual(motd_bytes.decode("utf-8"), "Welcome to Virtual Pywer!")

        # Test lifecycle
        plugin.on_enable()
        self.assertTrue(plugin.enable_called)
        plugin.on_disable()
        self.assertTrue(plugin.disable_called)

    def test_plugin_config_persistence(self):
        pkg_path = self._build_test_plugin()
        plugin = VirtualPluginLoader.load_plugin(pkg_path, self.server, self.data_dir)

        # Default config operations
        self.assertIsInstance(plugin.config, PluginConfig)
        plugin.config.set("max_players", 50)
        plugin.config.set("pvp_enabled", False)
        plugin.config.save()

        # Check config file exists on disk in data_folder
        cfg_file = plugin.data_folder / "config.json"
        self.assertTrue(cfg_file.exists())

        # Reload and verify
        plugin.config.reload()
        self.assertEqual(plugin.config.get("max_players"), 50)
        self.assertEqual(plugin.config.get("pvp_enabled"), False)
        self.assertEqual(plugin.config.get("non_existent", "default_val"), "default_val")

    def test_multiple_isolated_plugins(self):
        # Create PluginA
        dir_a = Path(self.temp_dir) / "src_a"
        dir_a.mkdir()
        with open(dir_a / "plugin.json", "w", encoding="utf-8") as f:
            json.dump({"name": "PluginA", "version": "1.0", "main": "main:PluginA", "api_version": "1.0"}, f)
        with open(dir_a / "main.py", "w", encoding="utf-8") as f:
            f.write("from pywer.plugin.base import PluginBase\nclass PluginA(PluginBase):\n    def get_id(self): return 'A'\n")
        pkg_a = PluginCompiler.pack(dir_a, self.dist_dir / "PluginA.pywer")

        # Create PluginB
        dir_b = Path(self.temp_dir) / "src_b"
        dir_b.mkdir()
        with open(dir_b / "plugin.json", "w", encoding="utf-8") as f:
            json.dump({"name": "PluginB", "version": "2.0", "main": "main:PluginB", "api_version": "1.0"}, f)
        with open(dir_b / "main.py", "w", encoding="utf-8") as f:
            f.write("from pywer.plugin.base import PluginBase\nclass PluginB(PluginBase):\n    def get_id(self): return 'B'\n")
        pkg_b = PluginCompiler.pack(dir_b, self.dist_dir / "PluginB.pywer")

        plugin_a = VirtualPluginLoader.load_plugin(pkg_a, self.server, self.data_dir)
        plugin_b = VirtualPluginLoader.load_plugin(pkg_b, self.server, self.data_dir)

        self.assertEqual(plugin_a.get_id(), "A")
        self.assertEqual(plugin_b.get_id(), "B")
        self.assertNotEqual(plugin_a.__module__, plugin_b.__module__)

    def test_invalid_plugin_class_not_subclassing_base(self):
        dir_c = Path(self.temp_dir) / "src_c"
        dir_c.mkdir()
        with open(dir_c / "plugin.json", "w", encoding="utf-8") as f:
            json.dump({"name": "PluginC", "version": "1.0", "main": "main:NotAPlugin", "api_version": "1.0"}, f)
        with open(dir_c / "main.py", "w", encoding="utf-8") as f:
            f.write("class NotAPlugin:\n    pass\n")
        pkg_c = PluginCompiler.pack(dir_c, self.dist_dir / "PluginC.pywer")

        with self.assertRaises(TypeError):
            VirtualPluginLoader.load_plugin(pkg_c, self.server, self.data_dir)


if __name__ == "__main__":
    unittest.main()
