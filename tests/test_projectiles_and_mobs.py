import unittest
from unittest.mock import MagicMock
from pywer.entity.projectile import Arrow, Snowball
from pywer.entity.mob import Cow, Zombie


class TestProjectilesAndMobs(unittest.TestCase):
    def test_arrow_properties_and_sticking(self):
        srv = MagicMock()
        arrow = Arrow(srv, 2001, shooter_rid=50, pos=(0, 65, 0), motion=(1.0, 0.0, 0.0))
        self.assertEqual(arrow.identifier, "minecraft:arrow")
        self.assertEqual(arrow.shooter_rid, 50)
        self.assertFalse(arrow.in_ground)
        self.assertEqual(arrow.damage, 4.0)

        # Sticking in ground
        arrow.stick_in_ground()
        self.assertTrue(arrow.in_ground)
        self.assertEqual(arrow.motion, (0.0, 0.0, 0.0))

        # Ticking in ground does not move
        moved = arrow.tick(0.0, 0.05, lambda x, y, z: True)
        self.assertFalse(moved)

    def test_snowball_properties(self):
        srv = MagicMock()
        snowball = Snowball(srv, 2002, shooter_rid=51, pos=(0, 65, 0), motion=(1.5, 0.2, 0.0))
        self.assertEqual(snowball.identifier, "minecraft:snowball")
        self.assertEqual(snowball.shooter_rid, 51)
        self.assertEqual(snowball.damage, 0.0)

    def test_living_mob_zombie_damage_and_targeting(self):
        srv = MagicMock()
        player = MagicMock()
        player.rid = 100
        player.feet.return_value = (12.0, 64.0, 10.0)
        player.gamemode_is_creative.return_value = False
        srv.playing.return_value = [player]

        zombie = Zombie(srv, 3001, pos=(10.0, 64.0, 10.0))
        self.assertEqual(zombie.identifier, "minecraft:zombie")
        self.assertEqual(zombie.health, 20.0)
        self.assertFalse(zombie.dead)

        # Damage zombie
        hit = zombie.damage(5.0, source_rid=50)
        self.assertTrue(hit)
        self.assertEqual(zombie.health, 15.0)

        # Hurt cooldown protects from immediate re-damage
        hit2 = zombie.damage(5.0, source_rid=50)
        self.assertFalse(hit2)
        self.assertEqual(zombie.health, 15.0)

        # Tick zombie AI: should target nearby survival player at (12, 64, 10)
        zombie.tick(1.0, 0.05, lambda x, y, z: False)
        self.assertEqual(zombie.ai_state, "TARGET")
        # Stepped along X towards 12
        self.assertGreater(zombie.pos[0], 10.0)

        # Lethal damage
        zombie.hurt_time = 0
        zombie.damage(25.0, source_rid=50)
        self.assertEqual(zombie.health, 0.0)
        self.assertTrue(zombie.dead)

    def test_passive_mob_cow(self):
        srv = MagicMock()
        srv.playing.return_value = []
        cow = Cow(srv, 3002, pos=(5.0, 64.0, 5.0))
        self.assertEqual(cow.identifier, "minecraft:cow")
        self.assertEqual(cow.health, 10.0)
        self.assertIn(cow.ai_state, ("IDLE", "WANDER"))


if __name__ == "__main__":
    unittest.main()
