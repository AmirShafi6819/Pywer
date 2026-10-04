"""Regression tests for server lifecycle: shutdown, persistence and ping response."""

import contextlib
import io
import signal
import sys
import unittest
from unittest import mock

from pywer import __version__, config
from pywer.protocol.inventory import CONTAINER_ID_FIRST
from pywer.server.main import make_shutdown_handler
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

    def test_motd_advertises_the_configured_player_limit(self):
        original = config.MAX_PLAYERS
        try:
            for limit in (1, 8, 32):
                config.MAX_PLAYERS = limit
                fields = build_motd(1, 19132).split(";")
                self.assertEqual(fields[5], str(limit))
        finally:
            config.MAX_PLAYERS = original

    def test_motd_reports_the_live_online_count(self):
        self.assertEqual(build_motd(1, 19132, online=0).split(";")[4], "0")
        self.assertEqual(build_motd(1, 19132, online=5).split(";")[4], "5")
        self.assertEqual(build_motd(1, 19132, online=-3).split(";")[4], "0")

    def test_motd_matches_the_package_version(self):
        self.assertTrue(
            build_motd(1, 19132).split(";")[1].endswith(__version__),
            "advertised version drifted from pywer.__version__",
        )

    def test_motd_fills_every_field(self):
        # An unconnected ping is a positional string: a missing argument here raises
        # on every ping and silently removes the server from the server list.
        fields = build_motd(99, 19132).split(";")
        # 12 payload fields plus the trailing separator.
        self.assertEqual(len(fields), 13)
        self.assertEqual(fields[-1], "")
        self.assertEqual(fields[6], "99")
        self.assertEqual(fields[10], "19132")
        self.assertEqual(fields[11], "19133")


def _sentinel_signal(*args):
    return None


class TestShutdownSignal(unittest.TestCase):
    def test_the_first_signal_starts_a_clean_shutdown(self):
        handler = make_shutdown_handler()
        saved = signal.getsignal(signal.SIGINT)
        try:
            signal.signal(signal.SIGINT, _sentinel_signal)
            with self.assertRaises(KeyboardInterrupt):
                handler(signal.SIGINT, None)
            self.assertTrue(handler.state["shutting_down"])
            # The clean shutdown owns the disposition; only a later signal may hand it
            # back to the OS.
            self.assertIs(signal.getsignal(signal.SIGINT), _sentinel_signal)
        finally:
            signal.signal(signal.SIGINT, saved)

    def test_a_later_signal_is_never_swallowed(self):
        handler = make_shutdown_handler()
        saved = signal.getsignal(signal.SIGINT)
        try:
            signal.signal(signal.SIGINT, _sentinel_signal)
            with self.assertRaises(KeyboardInterrupt):
                handler(signal.SIGINT, None)
            # A hung on_disable()/world write used to hit `return` here, leaving the
            # operator unable to stop the process without a second terminal.
            with self.assertRaises(KeyboardInterrupt):
                handler(signal.SIGINT, None)
            self.assertIs(signal.getsignal(signal.SIGINT), signal.SIG_DFL)
            # The disposition stays default, so the next Ctrl+C terminates outright.
            self.assertIs(signal.getsignal(signal.SIGINT), signal.SIG_DFL)
        finally:
            signal.signal(signal.SIGINT, saved)

    def test_each_signal_is_restored_independently(self):
        handler = make_shutdown_handler()
        saved_int = signal.getsignal(signal.SIGINT)
        saved_term = signal.getsignal(signal.SIGTERM)
        try:
            signal.signal(signal.SIGINT, _sentinel_signal)
            signal.signal(signal.SIGTERM, _sentinel_signal)
            with self.assertRaises(KeyboardInterrupt):
                handler(signal.SIGINT, None)
            with self.assertRaises(KeyboardInterrupt):
                handler(signal.SIGTERM, None)
            self.assertIs(signal.getsignal(signal.SIGTERM), signal.SIG_DFL)
            self.assertIs(signal.getsignal(signal.SIGINT), _sentinel_signal)
        finally:
            signal.signal(signal.SIGINT, saved_int)
            signal.signal(signal.SIGTERM, saved_term)


class _SlowShutdownServer:
    """A server whose persistence finishes only after run() is interrupted."""

    def __init__(self, *args, **kwargs):
        pass

    def banner(self):
        pass

    def run(self):
        raise KeyboardInterrupt

    def stop(self):
        print("[INFO] [Storage] saved world and player data", flush=True)


class TestConsoleOrdering(unittest.TestCase):
    def test_bye_is_printed_after_persistence_completes(self):
        saved_argv = sys.argv
        saved_int = signal.getsignal(signal.SIGINT)
        saved_term = signal.getsignal(signal.SIGTERM)
        sys.argv = ["pywer"]
        out = io.StringIO()
        try:
            with mock.patch("pywer.server.main.Server", _SlowShutdownServer):
                with contextlib.redirect_stdout(out):
                    from pywer.server.main import main

                    main()
        finally:
            sys.argv = saved_argv
            signal.signal(signal.SIGINT, saved_int)
            signal.signal(signal.SIGTERM, saved_term)

        text = out.getvalue()
        self.assertIn("saved world and player data", text)
        self.assertIn("bye", text)
        self.assertLess(
            text.index("saved world and player data"),
            text.index("bye"),
            "console said bye before the world was saved",
        )


if __name__ == "__main__":
    unittest.main()
