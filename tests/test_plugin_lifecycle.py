"""Unit tests for PluginManager lifecycle, dependency resolution, and auto-cleanup."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import List

from pywer.command import Command, CommandManager, CommandSender
from pywer.event import (
    EventManager,
    Listener,
    listen,
    PlayerJoinEvent,
    PluginDisableEvent,
    PluginEnableEvent,
)
from pywer.plugin.base import PluginBase
from pywer.plugin.compiler import PluginCompiler
from pywer.plugin.manager import PluginManager
from pywer.scheduler import ServerScheduler


class DummyServer:
    def __init__(self):
        self.event_manager = EventManager()
        self.command_manager = CommandManager(self)
        self.scheduler = ServerScheduler(self)


class TestPluginLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="pywer_test_lifecycle_")
        self.plugins_dir = Path(self.temp_dir) / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = self.plugins_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.server = DummyServer()
        self.mgr = PluginManager(self.server, self.plugins_dir, self.data_dir)

    def tearDown(self):
        self.mgr.disable_all()
        self.server.scheduler.shutdown()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_plugin_pkg(self, name: str, deps: List[str] = None, main_code: str = "") -> Path:
        src = Path(self.temp_dir) / f"src_{name}"
        src.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": name,
            "version": "1.0.0",
            "main": f"main:{name}",
            "api_version": "1.0.0",
            "dependencies": deps or [],
        }
        with open(src / "plugin.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        default_code = f"""from pywer.plugin.base import PluginBase
class {name}(PluginBase):
    def __init__(self):
        super().__init__()
        self.enabled = False
        self.disabled = False
    def on_enable(self):
        self.enabled = True
    def on_disable(self):
        self.disabled = True
"""
        code = main_code or default_code
        with open(src / "main.py", "w", encoding="utf-8") as f:
            f.write(code)

        pkg_path = self.plugins_dir / f"{name}.pywer"
        return PluginCompiler.pack(src, pkg_path)

    def test_dependency_resolution_order(self):
        # PluginA depends on PluginB
        self._create_plugin_pkg("PluginA", deps=["PluginB"])
        self._create_plugin_pkg("PluginB")

        loaded = self.mgr.load_all_plugins()
        names = [p.name for p in loaded]

        self.assertEqual(names, ["PluginB", "PluginA"])

    def test_disable_cleans_up_all_subsystems(self):
        main_code = """from pywer.plugin.base import PluginBase
from pywer.event import Listener, listen, PlayerJoinEvent
from pywer.command import Command

class ActivePlugin(PluginBase):
    def on_enable(self):
        self.join_count = 0
        self.tick_count = 0

        # Register event
        class JoinListener(Listener):
            @listen()
            def on_join(l_self, event: PlayerJoinEvent):
                self.join_count += 1

        self.register_listener(JoinListener())

        # Register command
        class TestCmd(Command):
            def __init__(self):
                super().__init__("plugincmd")
            def execute(cmd_self, sender, args):
                sender.send_message("ok")
                return True

        self.register_command(TestCmd())

        # Register repeating task
        def tick_task():
            self.tick_count += 1

        self.run_repeating(1, 1, tick_task)
"""
        pkg = self._create_plugin_pkg("ActivePlugin", main_code=main_code)
        self.mgr.load_all_plugins()
        self.mgr.enable_all()

        plugin = self.mgr.get_plugin("ActivePlugin")
        self.assertIsNotNone(plugin)
        self.assertTrue(plugin.is_enabled)

        # Verify command registered
        self.assertIsNotNone(self.server.command_manager.get_command("plugincmd"))

        # Verify event listener active
        self.server.event_manager.call(PlayerJoinEvent(None, "Hello"))
        self.assertEqual(plugin.join_count, 1)

        # Verify scheduled task ticking
        self.server.scheduler.tick()
        self.assertEqual(plugin.tick_count, 1)

        # Disable the plugin
        self.mgr.disable_plugin(plugin)
        self.assertFalse(plugin.is_enabled)

        # 1. Event listener must be detached
        self.server.event_manager.call(PlayerJoinEvent(None, "Hello again"))
        self.assertEqual(plugin.join_count, 1)  # No change

        # 2. Command must be unregistered
        self.assertIsNone(self.server.command_manager.get_command("plugincmd"))

        # 3. Scheduled task must be cancelled
        self.server.scheduler.tick()
        self.assertEqual(plugin.tick_count, 1)  # No change

    def test_enable_disable_events(self):
        fired_events = []

        class LifecycleListener(Listener):
            @listen()
            def on_enable(self, event: PluginEnableEvent):
                fired_events.append(("ENABLE", event.plugin.name))

            @listen()
            def on_disable(self, event: PluginDisableEvent):
                fired_events.append(("DISABLE", event.plugin.name))

        self.server.event_manager.register_listener(LifecycleListener())

        self._create_plugin_pkg("EventPlugin")
        self.mgr.load_all_plugins()
        self.mgr.enable_all()
        self.assertEqual(fired_events, [("ENABLE", "EventPlugin")])

        self.mgr.disable_all()
        self.assertEqual(fired_events, [("ENABLE", "EventPlugin"), ("DISABLE", "EventPlugin")])

    def test_reload_plugin(self):
        self._create_plugin_pkg("ReloadablePlugin")
        self.mgr.load_all_plugins()
        self.mgr.enable_all()

        p1 = self.mgr.get_plugin("ReloadablePlugin")
        self.assertTrue(p1.is_enabled)

        p2 = self.mgr.reload_plugin("ReloadablePlugin")
        self.assertIsNotNone(p2)
        self.assertTrue(p2.is_enabled)
        self.assertFalse(p1.is_enabled)
        self.assertIs(self.mgr.get_plugin("ReloadablePlugin"), p2)


if __name__ == "__main__":
    unittest.main()
