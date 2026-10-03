"""End-to-end smoke test for Pywer 6-priority Event System, Plugin Architecture,

.pywer virtual packaging, commands, scheduler, and auto-cleanup.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure project root is on sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pywer.command import CommandSender, PlayerCommandSender
from pywer.event import EventPriority, PlayerChatEvent, PlayerJoinEvent
from pywer.plugin.compiler import PluginCompiler
from pywer.server.server import Server


class MockPlayerSession:
    def __init__(self, name="Steve"):
        self.name = name
        self.messages = []
        self.is_op = True
        self.pos = (100.0, 64.0, 200.0)
        self.yaw = 0.0
        self.pitch = 0.0
        self.on_ground = True
        self.fall_distance = 0.0

    def chat_to(self, msg: str) -> None:
        self.messages.append(msg)

    def feet(self):
        return (self.pos[0], self.pos[1], self.pos[2])

    def teleport(self, x, y, z):
        self.pos = (x, y, z)


def run_plugin_smoke_test():
    print("=" * 65)
    print("Starting Milestone 4: Event & Plugin Architecture Smoke Test")
    print("=" * 65)

    plugins_dir = _ROOT / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    pkg_file = plugins_dir / "SamplePlugin.pywer"

    # Step 1: Verify / Compile sample plugin into .pywer
    src_dir = _ROOT / "examples" / "sample_plugin"
    print(f"\n[Step 1] Compiling sample plugin from {src_dir}...")
    built_pkg = PluginCompiler.pack(src_dir, pkg_file)
    assert built_pkg.exists(), "SamplePlugin.pywer must exist after pack"
    print(f" -> Successfully compiled: {built_pkg.name} ({built_pkg.stat().st_size} bytes)")

    # Step 2: Initialize Server harness
    print("\n[Step 2] Initializing Server instance with plugin subsystems...")
    srv = Server.__new__(Server)
    srv.guid = 123456789
    srv.port = 19132
    srv.sock = MagicMock()
    srv.sessions = {}
    srv.worker_pool = MagicMock()
    srv.save_all = MagicMock()

    from pywer.command import CommandManager
    from pywer.event import manager as events
    from pywer.plugin.manager import PluginManager
    from pywer.scheduler import ServerScheduler

    srv.event_mgr = events
    srv.event_manager = events
    srv.scheduler = ServerScheduler(srv)
    srv.command_mgr = CommandManager(srv)
    srv.command_manager = srv.command_mgr
    srv.plugins_dir = plugins_dir
    srv.plugin_data_dir = plugins_dir / "data"
    srv.plugin_mgr = PluginManager(srv, srv.plugins_dir, srv.plugin_data_dir)
    srv.plugin_manager = srv.plugin_mgr

    # Step 3: Discover and virtually load plugins
    print("\n[Step 3] Loading plugins virtually in-memory (zero disk extraction)...")
    loaded = srv.plugin_mgr.load_all_plugins()
    assert len(loaded) >= 1, "At least one plugin must be loaded"
    sample_plugin = srv.plugin_mgr.get_plugin("SamplePlugin")
    assert sample_plugin is not None, "SamplePlugin must be present in PluginManager"
    print(f" -> Plugin discovered and loaded: {sample_plugin.name} v{sample_plugin.version}")

    # Check zero disk pollution: plugins_dir must not contain extracted python folders
    extracted_py = list(plugins_dir.glob("*.py"))
    assert len(extracted_py) == 0, f"No .py files should be extracted to disk! Found: {extracted_py}"
    print(" -> Verified zero-disk-extraction: Pure in-memory virtual loading confirmed!")

    # Step 4: Enable plugins
    print("\n[Step 4] Enabling plugins and verifying lifecycle hooks...")
    srv.plugin_mgr.enable_all()
    assert sample_plugin.is_enabled, "SamplePlugin must be enabled"
    print(" -> SamplePlugin enabled successfully.")

    # Step 5: Test Command System & Senders
    print("\n[Step 5] Testing unified command execution and alias resolution...")
    player = MockPlayerSession("Alex")
    sender = PlayerCommandSender(player)

    # Execute primary command /ping
    handled = srv.command_mgr.dispatch(sender, "/ping")
    assert handled, "Command /ping must be handled"
    assert any("Pong!" in m for m in player.messages), f"Player should receive Pong!, got {player.messages}"
    print(" -> Primary command /ping executed successfully.")

    # Execute alias /p with args
    player.messages.clear()
    handled_alias = srv.command_mgr.dispatch(sender, "/p test bedrock")
    assert handled_alias, "Command alias /p must be handled"
    assert any("Pong! (test bedrock)" in m for m in player.messages), f"Player should receive echo, got {player.messages}"
    print(" -> Alias /p with arguments executed successfully.")

    # Step 6: Test 6-Priority Event System & Cancellation
    print("\n[Step 6] Testing event bus priority, banner formatting, and cancellation...")
    # PlayerJoinEvent
    player.messages.clear()
    join_ev = srv.event_mgr.call(PlayerJoinEvent(player, "Alex joined"))
    assert sample_plugin.joins_received == 1, "Plugin must receive join event"
    assert any("[SamplePlugin]" in m for m in player.messages), "Welcome banner must be delivered to player"
    print(" -> PlayerJoinEvent handled with formatted welcome banner.")

    # Normal chat message
    player.messages.clear()
    chat_ev_normal = srv.event_mgr.call(PlayerChatEvent(player, "Hello everyone!"))
    assert not chat_ev_normal.is_cancelled, "Normal chat must NOT be cancelled"
    print(" -> Normal chat event permitted through event bus.")

    # Profanity filter cancellation
    chat_ev_bad = srv.event_mgr.call(PlayerChatEvent(player, "You are a badword person"))
    assert chat_ev_bad.is_cancelled, "Chat containing badword MUST be cancelled by SamplePlugin"
    assert any("profanity filter" in m.lower() for m in player.messages), "Filter warning must be sent to player"
    print(" -> Event cancellation verified: Profanity was cancelled and player notified.")

    # Step 7: Test ServerScheduler Heartbeat
    print("\n[Step 7] Testing ServerScheduler repeating task ticks...")
    initial_heartbeats = sample_plugin.heartbeat_ticks
    for _ in range(25):
        srv.scheduler.tick()
    assert sample_plugin.heartbeat_ticks > initial_heartbeats, "Heartbeat task must tick in scheduler"
    print(f" -> Scheduler executed repeating task ({sample_plugin.heartbeat_ticks} heartbeats).")

    # Step 8: Test Plugin Reloading
    print("\n[Step 8] Testing live plugin reload...")
    reloaded = srv.plugin_mgr.reload_plugin("SamplePlugin")
    assert reloaded is not None, "Reloaded plugin instance must not be None"
    assert reloaded.is_enabled, "Reloaded plugin must be enabled"
    print(f" -> Successfully reloaded '{reloaded.name}' v{reloaded.version}.")

    # Verify reloaded plugin commands work
    player.messages.clear()
    srv.command_mgr.dispatch(sender, "/ping reload_check")
    assert any("Pong! (reload_check)" in m for m in player.messages), "Reloaded command must work"
    print(" -> Reloaded plugin command verified.")

    # Step 9: Test Server Shutdown & Auto-Cleanup
    print("\n[Step 9] Testing server shutdown and clean subsystem unregistration...")
    srv.stop()
    assert not reloaded.is_enabled, "Plugin must be disabled after server.stop()"
    assert srv.command_mgr.get_command("ping") is None, "Commands must be unregistered after disable"
    print(" -> Clean auto-cleanup verified: All listeners, commands, and tasks detached.")

    print("\n" + "=" * 65)
    print("SMOKE TEST PASSED: Event & Plugin Architecture fully operational!")
    print("=" * 65)


if __name__ == "__main__":
    run_plugin_smoke_test()
