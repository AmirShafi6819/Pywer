"""Unit tests for CommandManager, CommandSender, PlayerCommandSender, and ConsoleCommandSender."""

import unittest
from typing import List
from unittest.mock import MagicMock

from pywer.command import (
    Command,
    CommandManager,
    CommandSender,
    ConsoleCommandSender,
    PlayerCommandSender,
)
from pywer.command import manager as command_manager_module
from pywer.data.item_table import ITEM_NAME
from pywer.event import EventManager, listen
from pywer.event.player import PlayerCommandPreprocessEvent
from pywer.player.inventory import INVENTORY_SIZE, ITEM_AIR, item_tuple
from pywer.world.blocks import ITEM_RUNTIME


class MockSession:
    def __init__(self, name="Steve"):
        self.name = name
        self.messages = []
        self.is_op = False
        self.pos = (0.0, 64.0, 0.0)
        self.inventory = [ITEM_AIR for _ in range(INVENTORY_SIZE)]
        self.teleported = []

    def chat_to(self, msg: str) -> None:
        self.messages.append(msg)

    def gamemode_is_creative(self) -> bool:
        return False

    def feet(self):
        return self.pos

    def teleport(self, x, y, z) -> None:
        self.teleported.append((x, y, z))


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


class TestBuiltInCommands(unittest.TestCase):
    """Exercises the commands the server registers at runtime.

    test_imports only imports each module, so a command whose data was resolved by
    a lazy import inside execute() was never actually run by that suite.
    """

    def setUp(self):
        self.mgr = CommandManager(server=MagicMock())
        self.session = MockSession("Alex")
        self.sender = PlayerCommandSender(self.session)

    def last_message(self) -> str:
        return self.session.messages[-1]

    def assert_internal_error_free(self):
        self.assertFalse(
            any("internal error" in m for m in self.session.messages),
            self.session.messages,
        )

    def test_registry_data_resolves_at_module_scope(self):
        self.assertTrue(command_manager_module.BLOCK_KEYS[1:])
        self.assertTrue(command_manager_module.ITEM_RUNTIME)
        self.assertTrue(command_manager_module.ITEM_NAME)
        self.assertEqual(command_manager_module.INVENTORY_SIZE, INVENTORY_SIZE)

    def test_item_name_has_a_single_definition(self):
        import pywer.server.server as server_module

        self.assertIs(command_manager_module.ITEM_NAME, ITEM_NAME)
        self.assertIs(server_module.ITEM_NAME, ITEM_NAME)

    def test_blocks_command_lists_registered_blocks(self):
        self.assertTrue(self.mgr.dispatch(self.sender, "/blocks"))
        listing = self.last_message()
        self.assertTrue(listing.startswith("blocks: "))
        self.assertIn("stone", listing)
        self.assertNotIn("air", listing)

    def test_items_command_lists_registered_items(self):
        self.assertTrue(self.mgr.dispatch(self.sender, "/items"))
        listing = self.last_message()
        self.assertTrue(listing.startswith("items: "))
        self.assertIn("stone", listing)
        self.assertNotIn("Error listing", listing)

    def test_inv_command_renders_item_names(self):
        rid = ITEM_RUNTIME["stone"]
        self.session.inventory[0] = item_tuple(rid, 5, 0)

        self.assertTrue(self.mgr.dispatch(self.sender, "/inv"))
        listing = self.last_message()
        self.assertIn("0:%s x5" % ITEM_NAME[rid], listing)
        self.assertNotIn("0:%d x5" % rid, listing)

    def test_give_rejects_invalid_amount_and_slot(self):
        for line in ("/give stone abc", "/give stone 1 noslot", "/give stone 0", "/give stone -3", "/give stone 5 99"):
            with self.subTest(line=line):
                self.session.messages.clear()
                self.mgr.server.give.reset_mock()

                self.assertFalse(self.mgr.dispatch(self.sender, line))
                self.assertTrue(any("Usage:" in m for m in self.session.messages))
                self.assert_internal_error_free()
                self.mgr.server.give.assert_not_called()

    def test_give_passes_valid_amount_and_slot_through(self):
        self.assertTrue(self.mgr.dispatch(self.sender, "/give stone 5 0"))
        self.mgr.server.give.assert_called_once_with(self.session, "stone", 5, 0)

    def test_tp_rejects_invalid_coordinates(self):
        for line in ("/tp a b c", "/tp nan nan nan", "/tp 1 2 inf", "/tp 1 2"):
            with self.subTest(line=line):
                self.session.messages.clear()

                self.assertFalse(self.mgr.dispatch(self.sender, line))
                self.assertTrue(any("Usage:" in m for m in self.session.messages))
                self.assert_internal_error_free()
                self.assertEqual(self.session.teleported, [])

    def test_tp_accepts_absolute_and_relative_coordinates(self):
        self.assertTrue(self.mgr.dispatch(self.sender, "/tp 10 70 ~"))
        self.assertEqual(self.session.teleported, [(10.0, 70.0, 0.0)])
        self.assertIn("teleported to 10.0 70.0 0.0", self.last_message())


if __name__ == "__main__":
    unittest.main()
