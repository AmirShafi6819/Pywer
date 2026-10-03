"""Unit tests for spatial chunk-bucketed EntityManager and simulation distance culling."""

import unittest
from unittest.mock import MagicMock
from pywer.entity.manager import EntityManager
from pywer.entity.item import ItemEntity
from pywer.entity.mob import Zombie


class TestEntityManager(unittest.TestCase):
    def test_spatial_bucketing(self):
        srv = MagicMock()
        srv.next_rid = 100
        srv.playing.return_value = []
        mgr = EntityManager(srv)

        item = mgr.spawn(ItemEntity, "stone", 1, pos=(18.0, 64.0, 34.0))
        self.assertEqual(item.rid, 100)
        # Chunk (1, 2)
        self.assertIn((1, 2), mgr.chunk_index)
        self.assertIn(item, mgr.chunk_index[(1, 2)])

        # Move to Chunk (2, 2)
        mgr.update_entity_pos(item, (33.0, 64.0, 34.0))
        self.assertNotIn(item, mgr.chunk_index.get((1, 2), set()))
        self.assertIn(item, mgr.chunk_index[(2, 2)])

    def test_simulation_distance_culling(self):
        srv = MagicMock()
        srv.next_rid = 200
        p = MagicMock()
        p.cx, p.cz = 0, 0
        srv.playing.return_value = [p]
        mgr = EntityManager(srv)

        # Entity in active chunk (0, 0)
        near_item = mgr.spawn(ItemEntity, "dirt", 1, pos=(5.0, 65.0, 5.0))
        # Entity far away in chunk (20, 20)
        far_item = mgr.spawn(ItemEntity, "sand", 1, pos=(320.0, 65.0, 320.0))

        world_is_solid = lambda x, y, z: y <= 63
        mgr.tick(0.0, 0.05, world_is_solid)

        # Near item ticked and moved down
        self.assertLess(near_item.pos[1], 65.0)
        # Far item culled from ticking
        self.assertEqual(far_item.pos[1], 65.0)

    def test_entities_near(self):
        srv = MagicMock()
        srv.next_rid = 300
        srv.playing.return_value = []
        mgr = EntityManager(srv)

        z1 = mgr.spawn(Zombie, pos=(10.0, 64.0, 10.0))
        z2 = mgr.spawn(Zombie, pos=(12.0, 64.0, 10.0))
        z3 = mgr.spawn(Zombie, pos=(50.0, 64.0, 50.0))

        near = mgr.entities_near((10.0, 64.0, 10.0), radius=5.0)
        self.assertIn(z1, near)
        self.assertIn(z2, near)
        self.assertNotIn(z3, near)

    def test_remove_entity(self):
        srv = MagicMock()
        srv.next_rid = 400
        srv.playing.return_value = []
        mgr = EntityManager(srv)

        item = mgr.spawn(ItemEntity, "stone", 1, pos=(0.0, 64.0, 0.0))
        rid = item.rid
        self.assertIn(rid, mgr.entities)
        self.assertIn(item, mgr.chunk_index[(0, 0)])

        mgr.remove(rid)
        self.assertNotIn(rid, mgr.entities)
        self.assertNotIn(item, mgr.chunk_index.get((0, 0), set()))
        self.assertTrue(item.dead)


if __name__ == "__main__":
    unittest.main()
