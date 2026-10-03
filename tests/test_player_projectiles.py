"""Unit tests for Bedrock actor packet encoders and player projectile firing pipeline."""

import unittest
from unittest.mock import MagicMock
from pywer.player.session import Session
from pywer.packets.entity import build_add_actor, build_remove_actor
from pywer.entity.projectile import Arrow, Snowball


class TestPlayerProjectiles(unittest.TestCase):
    def test_build_add_actor_wire_format(self):
        arrow = Arrow(MagicMock(), 9001, 100, pos=(1.0, 64.0, 1.0), motion=(0.5, 0.0, 0.5))
        payload = build_add_actor(arrow)
        self.assertIsInstance(payload, bytes)
        self.assertGreater(len(payload), 10)
        self.assertIn(b"minecraft:arrow", payload)

    def test_build_remove_actor_wire_format(self):
        payload = build_remove_actor(9001)
        self.assertIsInstance(payload, bytes)
        self.assertGreater(len(payload), 0)

    def test_bow_release_spawns_arrow_and_consumes_inventory(self):
        srv = MagicMock()
        srv.next_rid = 1
        srv.key = (MagicMock(), MagicMock())
        srv.entity_mgr = MagicMock()
        sess = Session(srv, ("127.0.0.1", 19132), 1400, 100)
        sess._set_feet((0, 64, 0))
        sess.inventory[0] = (261, 1, 0)  # Bow in slot 0
        sess.inventory[9] = (262, 5, 0)  # 5 Arrows in slot 9
        sess.selected_slot = 0
        sess.gamemode_is_creative = lambda: False

        # Release bow transaction
        tx = {"action": 0, "hotbar": 0, "item": {"id": 261}}
        res = sess.handle_release_item(tx)
        self.assertTrue(res)

        # Arrow spawned via entity_mgr
        srv.entity_mgr.spawn.assert_called()
        spawn_args = srv.entity_mgr.spawn.call_args
        self.assertEqual(spawn_args[0][0], Arrow)
        # 1 arrow consumed from inventory
        self.assertEqual(sess.inventory[9], (262, 4, 0))

    def test_bow_release_no_arrows_fails_in_survival(self):
        srv = MagicMock()
        srv.next_rid = 1
        srv.key = (MagicMock(), MagicMock())
        srv.entity_mgr = MagicMock()
        sess = Session(srv, ("127.0.0.1", 19132), 1400, 100)
        sess._set_feet((0, 64, 0))
        sess.inventory[0] = (261, 1, 0)  # Bow in slot 0
        # No arrows in inventory
        sess.selected_slot = 0
        sess.gamemode_is_creative = lambda: False

        tx = {"action": 0, "hotbar": 0, "item": {"id": 261}}
        res = sess.handle_release_item(tx)
        self.assertFalse(res)
        srv.entity_mgr.spawn.assert_not_called()

    def test_snowball_throw_spawns_snowball_and_consumes_inventory(self):
        srv = MagicMock()
        srv.next_rid = 1
        srv.key = (MagicMock(), MagicMock())
        srv.entity_mgr = MagicMock()
        sess = Session(srv, ("127.0.0.1", 19132), 1400, 100)
        sess._set_feet((0, 64, 0))
        sess.inventory[0] = (332, 16, 0)  # Snowballs in slot 0
        sess.selected_slot = 0
        sess.gamemode_is_creative = lambda: False

        tx = {"action": 1, "hotbar": 0, "item": {"id": 332}}
        res = sess.handle_use_item(tx)
        self.assertTrue(res)

        srv.entity_mgr.spawn.assert_called()
        spawn_args = srv.entity_mgr.spawn.call_args
        self.assertEqual(spawn_args[0][0], Snowball)
        self.assertEqual(sess.inventory[0], (332, 15, 0))


if __name__ == "__main__":
    unittest.main()
