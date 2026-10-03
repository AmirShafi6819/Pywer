import unittest
from unittest.mock import MagicMock, patch
from pywer.player.session import Session
from pywer.server.server import Server
from pywer.protocol.inventory import WINDOW_WORKBENCH, WINDOW_CONTAINER

ITEM_AIR = (0, 0, 0)


class TestBlockContainers(unittest.TestCase):
    def setUp(self):
        self.srv = MagicMock()
        self.srv.next_rid = 1
        self.srv.key = (MagicMock(), MagicMock())
        self.srv.next_window_id.return_value = 5
        self.srv.container_id.return_value = 5
        self.srv.chests = {}
        self.sess = Session(self.srv, ("127.0.0.1", 19132), 1400, 100)
        self.sess.send_packet = MagicMock()
        self.sess._set_feet((10.0, 64.0, 10.0))

    def test_open_crafting_table(self):
        pos = (10, 64, 10)
        self.sess.open_crafting_table(pos)
        self.assertTrue(self.sess.open_window)
        self.assertEqual(self.sess.open_window_id, 5)
        self.assertEqual(self.sess.open_window_type, WINDOW_WORKBENCH)
        self.assertEqual(self.sess.open_window_pos, pos)
        self.sess.send_packet.assert_called()

    def test_open_chest(self):
        pos = (12, 64, 12)
        self.sess.open_chest(pos)
        self.assertTrue(self.sess.open_window)
        self.assertEqual(self.sess.open_window_id, 5)
        self.assertEqual(self.sess.open_window_type, WINDOW_CONTAINER)
        self.assertEqual(self.sess.open_window_pos, pos)
        self.assertIn(pos, self.srv.chests)
        self.assertEqual(len(self.srv.chests[pos]), 27)

    def test_resolve_chest_slot(self):
        pos = (12, 64, 12)
        self.sess.open_chest(pos)
        self.srv.chests[pos][0] = (1, 64, 0)  # 64 stone in slot 0

        # Resolve slot 0 of chest window 5
        r = self.sess.resolve_slot(5, 0)
        self.assertIsNotNone(r)
        cid, cont, slot = r
        self.assertEqual(slot, 0)
        self.assertEqual(cont[0], (1, 64, 0))

    @patch("pywer.player.session.get_block")
    def test_try_place_interacts_with_containers(self, mock_get_block):
        mock_get_block.return_value = "crafting_table"
        tx = {
            "face": 1,
            "pos": (10, 64, 10),
            "block_runtime_id": 0,
        }
        self.sess.sneaking = False
        res = self.sess.try_place_block(tx)
        self.assertTrue(res)
        self.assertTrue(self.sess.open_window)
        self.assertEqual(self.sess.open_window_type, WINDOW_WORKBENCH)

    @patch("pywer.server.server.get_block")
    def test_break_chest_drops_contents(self, mock_get_block):
        mock_get_block.return_value = "chest"
        srv = Server.__new__(Server)
        srv.chests = {(5, 64, 5): [ITEM_AIR] * 27}
        srv.chests[(5, 64, 5)][0] = (1, 32, 0)  # 32 stone
        srv.set_block = MagicMock(return_value=True)
        srv.drop_item = MagicMock(return_value=True)

        res = Server.break_block(srv, None, 5, 64, 5, old_key="chest")
        self.assertTrue(res)
        self.assertNotIn((5, 64, 5), srv.chests)
        srv.drop_item.assert_called_with((5.5, 65.0, 5.5), "stone", 32)


if __name__ == "__main__":
    unittest.main()
