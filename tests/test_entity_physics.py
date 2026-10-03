"""Unit tests for discrete raycasting and entity collision physics."""

import unittest
from unittest.mock import MagicMock
from pywer.entity.physics import (
    raycast_step,
    aabb_intersects_ray,
    check_projectile_collisions,
)
from pywer.entity.projectile import Arrow
from pywer.entity.mob import Zombie


class TestEntityPhysics(unittest.TestCase):
    def test_raycast_hits_block(self):
        # Ray from (0.5, 64.5, 0.5) with motion (2.0, 0.0, 0.0) towards solid block at x=2
        world_is_solid = lambda x, y, z: x >= 2
        hit_type, hit_pos, block_pos, face = raycast_step(
            (0.5, 64.5, 0.5), (2.0, 0.0, 0.0), world_is_solid
        )
        self.assertEqual(hit_type, "block")
        self.assertEqual(block_pos[0], 2)
        self.assertAlmostEqual(hit_pos[1], 64.5)

    def test_raycast_miss(self):
        world_is_solid = lambda x, y, z: False
        hit_type, hit_pos, block_pos, face = raycast_step(
            (0.0, 64.0, 0.0), (1.0, 0.0, 0.0), world_is_solid
        )
        self.assertEqual(hit_type, "none")
        self.assertIsNone(block_pos)
        self.assertIsNone(face)
        self.assertEqual(hit_pos, (1.0, 64.0, 0.0))

    def test_aabb_intersects_ray(self):
        # Target AABB at [5, 64, 5] to [6, 66, 6]
        target_aabb = (5.0, 64.0, 5.0, 6.0, 66.0, 6.0)
        # Ray starting at (0, 65, 5.5) moving +x towards (10, 65, 5.5)
        hit = aabb_intersects_ray(target_aabb, (0.0, 65.0, 5.5), (10.0, 0.0, 0.0))
        self.assertTrue(hit)
        # Ray aimed away
        miss = aabb_intersects_ray(target_aabb, (0.0, 65.0, 5.5), (0.0, 10.0, 0.0))
        self.assertFalse(miss)

    def test_check_projectile_collisions_block(self):
        srv = MagicMock()
        arrow = Arrow(srv, 100, shooter_rid=1, pos=(0.0, 64.0, 0.0), motion=(3.0, 0.0, 0.0))
        world_is_solid = lambda x, y, z: x >= 2
        hit_type, target_or_block, hit_pos = check_projectile_collisions(arrow, [], world_is_solid)
        self.assertEqual(hit_type, "block")
        block_pos, face = target_or_block
        self.assertEqual(block_pos[0], 2)

    def test_check_projectile_collisions_entity(self):
        srv = MagicMock()
        arrow = Arrow(srv, 100, shooter_rid=1, pos=(0.0, 64.0, 0.0), motion=(5.0, 0.0, 0.0))
        zombie = Zombie(srv, 200, pos=(3.0, 64.0, 0.0))
        world_is_solid = lambda x, y, z: False
        hit_type, target_or_block, hit_pos = check_projectile_collisions(arrow, [zombie], world_is_solid)
        self.assertEqual(hit_type, "entity")
        self.assertEqual(target_or_block, zombie)

    def test_check_projectile_collisions_shooter_immunity(self):
        srv = MagicMock()
        # Arrow fired by shooter 1, shooter 1 is inside or near the arrow at spawn (age = 0.0)
        arrow = Arrow(srv, 100, shooter_rid=1, pos=(0.0, 64.0, 0.0), motion=(1.0, 0.0, 0.0))
        shooter = Zombie(srv, 1, pos=(0.0, 64.0, 0.0))
        world_is_solid = lambda x, y, z: False
        hit_type, target_or_block, hit_pos = check_projectile_collisions(arrow, [shooter], world_is_solid)
        self.assertEqual(hit_type, "none")


if __name__ == "__main__":
    unittest.main()
