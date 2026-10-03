import unittest
from unittest.mock import MagicMock
from pywer.entity.base import Entity
from pywer.entity.item import ItemEntity


class TestEntityHierarchy(unittest.TestCase):
    def test_entity_base_properties(self):
        srv = MagicMock()
        e = Entity(
            srv,
            1001,
            pos=(18.5, 64.0, 32.5),
            motion=(0.1, 0.2, 0.3),
            pitch=10.0,
            yaw=45.0,
        )
        self.assertEqual(e.rid, 1001)
        self.assertEqual(e.pos, (18.5, 64.0, 32.5))
        self.assertEqual(e.motion, (0.1, 0.2, 0.3))
        self.assertEqual(e.pitch, 10.0)
        self.assertEqual(e.yaw, 45.0)
        self.assertEqual(e.chunk, (1, 2))  # 18 >> 4, 32 >> 4
        self.assertFalse(e.dead)
        self.assertFalse(e.on_ground)

        aabb = e.aabb()
        self.assertEqual(len(aabb), 6)
        self.assertLess(aabb[0], aabb[3])
        self.assertLess(aabb[1], aabb[4])
        self.assertLess(aabb[2], aabb[5])

    def test_item_entity_physics_and_merging(self):
        srv = MagicMock()
        item = ItemEntity(
            srv,
            1002,
            "stone",
            16,
            pos=(0.0, 65.0, 0.0),
            motion=(0.0, 0.0, 0.0),
            spawned_at=0.0,
        )
        self.assertEqual(item.item_key, "stone")
        self.assertEqual(item.count, 16)
        self.assertEqual(item.identifier, "minecraft:item")

        # Mock world_is_solid: solid only at y <= 63
        world_is_solid = lambda x, y, z: y <= 63
        moved = item.tick(0.05, 0.05, world_is_solid)
        self.assertTrue(moved)
        self.assertLess(item.pos[1], 65.0)  # Gravity pulled it down

        # Pickup check: within 1.5 blocks after pickup delay
        self.assertFalse(item.can_pickup((0.0, 64.0, 0.0), now=0.1))  # Delay not passed
        self.assertTrue(item.can_pickup((0.0, item.pos[1], 0.0), now=1.0))  # Can pickup
        self.assertFalse(item.can_pickup((10.0, 64.0, 10.0), now=1.0))  # Too far away


if __name__ == "__main__":
    unittest.main()
