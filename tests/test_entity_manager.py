"""Unit tests for spatial chunk-bucketed EntityManager and simulation distance culling."""

import unittest
from unittest.mock import MagicMock

from pywer.entity.manager import EntityManager
from pywer.entity.item import ItemEntity
from pywer.entity.mob import Zombie
from pywer.player.inventory import ITEM_AIR, MAX_STACK, item_tuple
from pywer.world.blocks import ITEM_RUNTIME


class FakePlayer:
    """Minimal player shape the manager actually consumes: pos, feet(), inventory, sync."""

    def __init__(self, pos, inventory=None):
        self.pos = pos
        self.inventory = inventory if inventory is not None else [ITEM_AIR] * 36
        self.syncs = 0

    def feet(self):
        return (self.pos[0], self.pos[1] - 1.62, self.pos[2])

    def sync_inventory(self):
        self.syncs += 1


def fake_server(players=(), rid=100):
    srv = MagicMock()
    srv.next_rid = rid
    srv.playing.return_value = list(players)
    return srv


def air_hole(item_id, fill_id, count):
    """A full inventory with room only for `count` more of `item_id`."""
    return [item_tuple(fill_id, 64, 0)] * 35 + [item_tuple(item_id, 64 - count, 0)]


def stack_total(inventory, item_id):
    return sum(st[1] for st in inventory if st[0] == item_id)


NO_FLOOR = lambda x, y, z: y <= 63


class TestEntityManager(unittest.TestCase):
    def test_spatial_bucketing(self):
        mgr = EntityManager(fake_server())

        item = mgr.spawn(ItemEntity, "stone", 1, pos=(18.0, 64.0, 34.0))
        self.assertEqual(item.rid, 100)
        # Chunk (1, 2)
        self.assertIn((1, 2), mgr.chunk_index)
        self.assertIn(item, mgr.chunk_index[(1, 2)])

        # Move to Chunk (2, 2)
        mgr.update_entity_pos(item, (33.0, 64.0, 34.0))
        self.assertNotIn(item, mgr.chunk_index.get((1, 2), set()))
        self.assertIn(item, mgr.chunk_index[(2, 2)])

    def test_simulation_distance_uses_the_player_chunk(self):
        # The simulation-distance window must be centred on the player's real chunk.
        # Reading a non-existent cx/x attribute used to anchor every player at (0, 0),
        # so nothing outside the origin ever ticked.
        player = FakePlayer((320.5, 65.0, 320.5))
        mgr = EntityManager(fake_server(players=[player]))

        near_item = mgr.spawn(ItemEntity, "dirt", 1, pos=(320.0, 65.0, 320.0))
        far_item = mgr.spawn(ItemEntity, "sand", 1, pos=(5.0, 65.0, 5.0))

        mgr.tick(0.0, 0.05, NO_FLOOR)

        self.assertLess(near_item.pos[1], 65.0)
        self.assertEqual(far_item.pos[1], 65.0)

    def test_entities_in_negative_chunks_are_bucketed_and_ticked(self):
        # int(-0.5) == 0, so truncation put an entity just west of the origin in chunk 0
        # while the player standing there belongs to chunk -1.
        player = FakePlayer((-5.0, 65.0, -5.0))
        mgr = EntityManager(fake_server(players=[player]))

        west = mgr.spawn(ItemEntity, "dirt", 1, pos=(-0.5, 65.0, -0.5))
        east = mgr.spawn(ItemEntity, "sand", 1, pos=(100.0, 65.0, 100.0))
        self.assertEqual(west.chunk, (-1, -1))

        mgr.tick(0.0, 0.05, NO_FLOOR)

        self.assertLess(west.pos[1], 65.0)
        self.assertEqual(east.pos[1], 65.0)

    def test_pickup_into_a_partial_stack_does_not_duplicate(self):
        dirt = ITEM_RUNTIME["dirt"]
        stone = ITEM_RUNTIME["stone"]
        player = FakePlayer((5.0, 65.0, 5.0), inventory=air_hole(dirt, stone, 4))
        mgr = EntityManager(fake_server(players=[player], rid=600))

        item = mgr.spawn(ItemEntity, "dirt", 20, pos=(5.0, 64.0, 5.0))
        item.pickup_at = 0.0
        mgr.tick(0.0, 0.05, NO_FLOOR)

        # Only 4 fitted: the rest must stay in the world, not be lost and not be doubled.
        self.assertEqual(stack_total(player.inventory, dirt), 64)
        self.assertEqual(stack_total(player.inventory, stone), 35 * 64)
        self.assertEqual(item.count, 16)
        self.assertIn(item.rid, mgr.entities)
        self.assertEqual(player.syncs, 1)

    def test_pickup_conserves_count_on_an_oversized_stack(self):
        dirt = ITEM_RUNTIME["dirt"]
        stone = ITEM_RUNTIME["stone"]
        # One empty slot only: 64 of the 100 fit, the rest must stay in the world.
        player = FakePlayer((5.0, 65.0, 5.0), inventory=air_hole(dirt, stone, 64))
        mgr = EntityManager(fake_server(players=[player], rid=700))

        item = mgr.spawn(ItemEntity, "dirt", 100, pos=(5.0, 64.0, 5.0))
        item.pickup_at = 0.0
        mgr.tick(0.0, 0.05, NO_FLOOR)

        picked = stack_total(player.inventory, dirt)
        self.assertEqual(picked + item.count, 100)
        self.assertEqual(picked, MAX_STACK)
        self.assertEqual(item.count, 36)
        self.assertIn(item.rid, mgr.entities)

    def test_pickup_removes_the_entity_once_empty(self):
        dirt = ITEM_RUNTIME["dirt"]
        player = FakePlayer((5.0, 65.0, 5.0))
        mgr = EntityManager(fake_server(players=[player], rid=800))

        item = mgr.spawn(ItemEntity, "dirt", 7, pos=(5.0, 64.0, 5.0))
        rid = item.rid
        item.pickup_at = 0.0
        mgr.tick(0.0, 0.05, NO_FLOOR)

        self.assertEqual(stack_total(player.inventory, dirt), 7)
        self.assertNotIn(rid, mgr.entities)

    def test_drop_item_merge_respects_the_stack_limit(self):
        mgr = EntityManager(fake_server(rid=900))
        first = mgr.spawn(ItemEntity, "dirt", 60, pos=(5.0, 64.0, 5.0))

        mgr.drop_item((5.2, 64.0, 5.2), "dirt", 20, now=0.0)

        stacks = [e for e in mgr.entities.values() if e.item_key == "dirt"]
        self.assertEqual(sum(e.count for e in stacks), 80)
        for e in stacks:
            self.assertLessEqual(e.count, MAX_STACK)
        self.assertEqual(first.count, MAX_STACK)

    def test_drop_item_splits_a_large_drop_into_stacks(self):
        mgr = EntityManager(fake_server(rid=910))
        mgr.drop_item((5.0, 64.0, 5.0), "dirt", 130, now=0.0)

        stacks = [e for e in mgr.entities.values() if e.item_key == "dirt"]
        self.assertEqual(sum(e.count for e in stacks), 130)
        self.assertEqual(max(e.count for e in stacks), MAX_STACK)
        self.assertEqual(len(stacks), 3)

    def test_entities_near(self):
        mgr = EntityManager(fake_server(rid=300))

        z1 = mgr.spawn(Zombie, pos=(10.0, 64.0, 10.0))
        z2 = mgr.spawn(Zombie, pos=(12.0, 64.0, 10.0))
        z3 = mgr.spawn(Zombie, pos=(50.0, 64.0, 50.0))

        near = mgr.entities_near((10.0, 64.0, 10.0), radius=5.0)
        self.assertIn(z1, near)
        self.assertIn(z2, near)
        self.assertNotIn(z3, near)

    def test_remove_entity(self):
        mgr = EntityManager(fake_server(rid=400))

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
