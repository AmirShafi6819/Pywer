"""Unit tests for CommandManager, CommandSender, PlayerCommandSender, and ConsoleCommandSender."""

import unittest
from typing import List

from pywer.command import (
    Command,
    CommandManager,
    CommandSender,
    ConsoleCommandSender,
    PlayerCommandSender,
)
from pywer.event import EventManager, listen
from pywer.event.player import PlayerCommandPreprocessEvent


class MockSession:
    def __init__(self, name="Steve"):
        self.name = name
        self.messages = []
        self.is_op = False
        self.pos = (0.0, 64.0, 0.0)

    def chat_to(self, msg: str) -> None:
        self.messages.append(msg)

    def gamemode_is_creative(self) -> bool:
        return False


class PingCommand(Command):
    def __init__(self):
        super().__init__(
            name="ping",
            description="Replies with pong",
            usage="/ping [arg]",
            aliases=["p", "pong"],
        )
        self.executed_with = []

    def execute(self, sender: CommandSender, args: List[str]) -> bool:
        self.executed_with.append((sender.name, args))
        sender.send_message("Pong!")
        return True


class SecretCommand(Command):
    def __init__(self):
        super().__init__(
            name="secret",
            description="Top secret admin command",
            permission="pywer.admin.secret",
        )
        self.executed = False

    def execute(self, sender: CommandSender, args: List[str]) -> bool:
        self.executed = True
        sender.send_message("Access granted.")
        return True


class TestCommandSystem(unittest.TestCase):
    def setUp(self):
        self.mgr = CommandManager()
        self.console = ConsoleCommandSender()
        self.session = MockSession("Alex")
        self.player_sender = PlayerCommandSender(self.session)

    def test_command_registration_and_execution(self):
        cmd = PingCommand()
        self.mgr.register_command(cmd)

        # Primary name
        result = self.mgr.dispatch(self.console, "/ping one two")
        self.assertTrue(result)
        self.assertEqual(cmd.executed_with[-1], ("CONSOLE", ["one", "two"]))

        # Alias and case insensitivity
        result_alias = self.mgr.dispatch(self.player_sender, "PONG test")
        self.assertTrue(result_alias)
        self.assertEqual(cmd.executed_with[-1], ("Alex", ["test"]))
        self.assertIn("Pong!", self.session.messages)

    def test_unknown_command(self):
        result = self.mgr.dispatch(self.console, "/nonexistent")
        self.assertFalse(result)

    def test_permission_checks(self):
        sec = SecretCommand()
        self.mgr.register_command(sec)

        # Non-op player sender should fail
        self.session.is_op = False
        res = self.mgr.dispatch(self.player_sender, "/secret")
        self.assertFalse(res)
        self.assertFalse(sec.executed)
        self.assertTrue(any("permission" in m.lower() for m in self.session.messages))

        # Op player sender should succeed
        self.session.is_op = True
        res_op = self.mgr.dispatch(self.player_sender, "/secret")
        self.assertTrue(res_op)
        self.assertTrue(sec.executed)

    def test_unregister_by_plugin(self):
        dummy_plugin = object()
        cmd = PingCommand()
        self.mgr.register_command(cmd, plugin=dummy_plugin)

        self.assertIsNotNone(self.mgr.get_command("ping"))
        self.assertIsNotNone(self.mgr.get_command("p"))

        unregistered = self.mgr.unregister_by_plugin(dummy_plugin)
        self.assertEqual(unregistered, 1)

        self.assertIsNone(self.mgr.get_command("ping"))
        self.assertIsNone(self.mgr.get_command("p"))

    def test_preprocess_event_cancellation(self):
        bus = EventManager()
        cancelled_called = []

        class PreprocessListener:
            @listen()
            def on_preprocess(self, event: PlayerCommandPreprocessEvent):
                if event.command.startswith("/blocked"):
                    event.cancel()
                    cancelled_called.append(True)

        bus.register_listener(PreprocessListener())

        ev = PlayerCommandPreprocessEvent(self.session, "/blocked command")
        bus.call(ev)
        self.assertTrue(ev.is_cancelled)
        self.assertEqual(cancelled_called, [True])


if __name__ == "__main__":
    unittest.main()
