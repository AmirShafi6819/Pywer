"""Regression tests for server lifecycle: shutdown, persistence and ping response."""

import unittest

from pywer import config
from pywer.protocol.inventory import CONTAINER_ID_FIRST
from pywer.server.server import GAMEMODE_NAMES, Server, build_motd


class Counter:
    def __init__(self, name, calls, fail=False):
        self.name = name
        self.calls = calls
        self.fail = fail

    def bump(self):
        self.calls.append(self.name)
        if self.fail:
            raise RuntimeError("%s exploded" % self.name)


class FakeEvents:
    def __init__(self, calls, fail=False):
        self.calls = calls
        self.fail = fail

    def call(self, event):
        Counter("event", self.calls, self.fail).bump()


class FakePlugins:
    def __init__(self, calls):
        self.calls = calls

    def disable_all(self):
        Counter("plugins", self.calls).bump()


class FakeScheduler:
    def __init__(self, calls):
        self.calls = calls

    def shutdown(self):
        Counter("scheduler", self.calls).bump()


class FakeWorkers:
    def __init__(self, calls):
        self.calls = calls

    def shutdown(self):
        Counter("workers", self.calls).bump()


class FakeWorldStorage:
    def __init__(self, calls):
        self.calls = calls

    def save(self, meta=None, edits=None):
        Counter("world", self.calls).bump()


class FakePlayerStorage:
    def __init__(self, calls):
        self.calls = calls

    def put(self, uuid, data):
        self.calls.append("player.put")

    def save(self, force=False):
        Counter("players", self.calls).bump()


class FakeSock:
    def __init__(self, calls):
        self.calls = calls

    def close(self):
        Counter("sock", self.calls).bump()


def bare_server(fail_event=False):
    """Build a Server without binding a socket, generating terrain or loading plugins."""
    calls = []
    srv = Server.__new__(Server)
    srv._stopped = False
    srv.sessions = {}
    srv._last_save = 0.0
    srv._window_id = CONTAINER_ID_FIRST + 5
    srv.event_mgr = FakeEvents(calls, fail=fail_event)
    srv.plugin_mgr = FakePlugins(calls)
    srv.scheduler = FakeScheduler(calls)
    srv.worker_pool = FakeWorkers(calls)
    srv.world_storage = FakeWorldStorage(calls)
    srv.player_storage = FakePlayerStorage(calls)
    srv.sock = FakeSock(calls)
    return srv, calls


class TestShutdown(unittest.TestCase):
    def test_stop_runs_every_step_and_closes_the_socket(self):
        srv, calls = bare_server()
        srv.stop()
        self.assertEqual(
            [c for c in calls if c != "player.put"],
            ["event", "plugins", "scheduler", "world", "players", "workers", "sock"],
        )
        self.assertTrue(srv._stopped)

    def test_stop_is_idempotent(self):
        srv, calls = bare_server()
        srv.stop()
        before = list(calls)
        srv.stop()
        srv.stop()
        self.assertEqual(calls, before)

    def test_stop_survives_a_failing_subsystem(self):
        srv, calls = bare_server(fail_event=True)
        srv.stop()
        # The ServerStopEvent failure must not prevent plugins/scheduler/save/sock cleanup.
        for expected in ("plugins", "scheduler", "world", "players", "workers", "sock"):
            self.assertIn(expected, calls)

    def test_stop_closes_the_socket_even_if_persist_fails(self):
        srv, calls = bare_server()
        srv.world_storage = None  # save_all raises AttributeError
        srv.stop()
        self.assertIn("sock", calls)
        self.assertTrue(srv._stopped)

    def test_shutdown_does_not_rewind_the_window_id_counter(self):
        srv, calls = bare_server()
        srv.stop()
        self.assertEqual(srv._window_id, CONTAINER_ID_FIRST + 5)


class TestMotd(unittest.TestCase):
    def test_motd_advertises_the_configured_game_mode(self):
        original = config.GAMEMODE
        try:
            for mode, name in GAMEMODE_NAMES.items():
                config.GAMEMODE = mode
                motd = build_motd(1, 19132)
                fields = motd.split(";")
                self.assertEqual(fields[7], "Minimal")
                self.assertEqual(fields[8], name, "mode %d" % mode)
                self.assertEqual(fields[9], str(mode & 0x7))
        finally:
            config.GAMEMODE = original

    def test_motd_survival_is_the_default_label(self):
        original = config.GAMEMODE
        try:
            config.GAMEMODE = 0
            self.assertIn(";Minimal;Survival;0;", build_motd(1, 19132))
        finally:
            config.GAMEMODE = original


if __name__ == "__main__":
    unittest.main()
