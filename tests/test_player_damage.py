"""Unit tests for player/mob damage: event wiring, health attribute sync, death and respawn."""

import struct
import unittest
from unittest.mock import MagicMock

from pywer.entity.mob import Zombie
from pywer.entity.projectile import Arrow
from pywer.event import (
    EntityDamageByEntityEvent,
    EntityDamageEvent,
    PlayerDeathEvent,
    PlayerRespawnEvent,
    manager as events,
)
from pywer.packets.entity import build_update_attributes
from pywer.player.movement import NETWORK_EYE_OFFSET
from pywer.player.session import Session
from pywer.protocol.packet_ids import PID_UPDATE_ATTRIBUTES
from pywer.server.server import Server


class TestPlayerDamage(unittest.TestCase):
    def setUp(self):
        self.srv = MagicMock()
        self.srv.next_rid = 1
        self.srv.key = (MagicMock(), MagicMock())
        self.srv.entity_mgr = MagicMock()
        self.srv.playing.return_value = []
        self.sess = Session(self.srv, ("127.0.0.1", 19132), 1400, 100)
        self.sess.send_packet = MagicMock()
        self.sess.send_packets = MagicMock()
        self.sess.teleport = MagicMock()
        self.sess._set_feet((0.0, 64.0, 0.0))
        self.sentinel = object()

    def tearDown(self):
        events.unregister_by_plugin(self.sentinel)

    def subscribe(self, event_cls, handler):
        events.subscribe(event_cls, handler, plugin=self.sentinel)

    def sent_pids(self):
        return [c[0][0] for c in self.sess.send_packet.call_args_list]

    # ---- health / attribute sync

    def test_damage_reduces_health_and_resends_attributes(self):
        self.assertTrue(self.sess.damage(4.0))
        self.assertEqual(self.sess.health, 16.0)
        self.assertIn(PID_UPDATE_ATTRIBUTES, self.sent_pids())
        self.assertIn(struct.pack("<f", 16.0), build_update_attributes(self.sess))

    def test_attribute_packet_uses_max_health_not_a_hardcoded_20(self):
        self.sess.max_health = 40.0
        self.sess.health = 40.0
        self.sess.damage(10.0)
        payload = build_update_attributes(self.sess)
        self.assertIn(struct.pack("<f", 40.0), payload)
        self.assertIn(struct.pack("<f", 30.0), payload)

    def test_damage_while_invulnerable_is_rejected(self):
        self.sess.hurt_time = 5
        self.assertFalse(self.sess.damage(4.0))
        self.assertEqual(self.sess.health, 20.0)
        self.assertNotIn(PID_UPDATE_ATTRIBUTES, self.sent_pids())

    def test_non_positive_damage_is_rejected(self):
        self.assertFalse(self.sess.damage(0.0))
        self.assertEqual(self.sess.health, 20.0)

    # ---- EntityDamageEvent wiring

    def test_damage_event_fires_with_amount_and_entity(self):
        seen = []
        self.subscribe(EntityDamageEvent, seen.append)
        self.sess.damage(4.0)
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0].entity, self.sess)
        self.assertAlmostEqual(seen[0].amount, 4.0)
        self.assertEqual(seen[0].cause, "entity_attack")

    def test_damage_event_cancellation_blocks_the_hit(self):
        self.subscribe(EntityDamageEvent, lambda ev: ev.cancel())
        self.assertFalse(self.sess.damage(4.0))
        self.assertEqual(self.sess.health, 20.0)

    def test_damage_event_can_rewrite_the_amount(self):
        self.subscribe(EntityDamageEvent, lambda ev: setattr(ev, "amount", 7.5))
        self.sess.damage(4.0)
        self.assertEqual(self.sess.health, 12.5)

    def test_melee_hit_uses_the_by_entity_event(self):
        attacker = Session(self.srv, ("127.0.0.1", 19132), 1400, 100)
        seen = []
        self.subscribe(EntityDamageByEntityEvent, seen.append)
        self.sess.damage(3.0, attacker)
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0].damager, attacker)
        self.assertEqual(self.sess.health, 17.0)

    def test_source_rid_resolves_to_the_shooting_player(self):
        shooter = Session(self.srv, ("127.0.0.1", 19132), 1400, 100)
        self.srv.playing.return_value = [shooter]
        seen = []
        self.subscribe(EntityDamageByEntityEvent, seen.append)
        self.sess.damage(3.0, source_rid=shooter.rid)
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0].damager, shooter)

    def test_projectile_hit_on_a_player_no_longer_raises(self):
        # Session.damage used to take only `attacker`, so a projectile hit blew up
        # with TypeError straight out of EntityManager.tick.
        shooter = Session(self.srv, ("127.0.0.1", 19132), 1400, 100)
        self.srv.playing.return_value = [shooter]
        arrow = Arrow(self.srv, 7000, shooter_rid=shooter.rid, pos=(0.0, 64.5, 0.0))
        arrow.on_hit_entity(self.sess, (0.0, 64.5, 0.0))
        self.assertTrue(arrow.dead)
        self.assertEqual(self.sess.health, 16.0)

    # ---- death and respawn

    def test_death_fires_death_and_respawn_events(self):
        deaths, respawns = [], []
        self.subscribe(PlayerDeathEvent, deaths.append)
        self.subscribe(PlayerRespawnEvent, respawns.append)
        self.sess.health = 2.0
        self.sess.damage(5.0)
        self.assertEqual(len(deaths), 1)
        self.assertIn("died", deaths[0].death_message)
        self.assertEqual(len(respawns), 1)
        self.assertEqual(respawns[0].respawn_pos[1], self.sess.teleport.call_args[0][1])
        self.assertEqual(self.sess.health, self.sess.max_health)
        self.assertFalse(self.sess.dead)

    def test_death_message_is_broadcast(self):
        self.sess.health = 2.0
        self.sess.damage(5.0)
        payloads = [pk for call in self.srv.broadcast.call_args_list for pk in call[0][0]]
        self.assertTrue(any(b"died" in p for p in payloads))

    def test_death_event_can_rewrite_the_message(self):
        def rewrite(ev):
            ev.death_message = "§ecustom message"

        self.subscribe(PlayerDeathEvent, rewrite)
        self.sess.health = 2.0
        self.sess.damage(5.0)
        payloads = [pk for call in self.srv.broadcast.call_args_list for pk in call[0][0]]
        self.assertTrue(any(b"custom message" in p for p in payloads))

    def test_death_resends_health_after_respawn(self):
        self.sess.health = 2.0
        self.sess.damage(5.0)
        health_payloads = [
            c[0][1] for c in self.sess.send_packet.call_args_list if c[0][0] == PID_UPDATE_ATTRIBUTES
        ]
        self.assertGreater(len(health_payloads), 1)
        self.assertIn(struct.pack("<f", 20.0), health_payloads[-1])

    def test_killer_named_in_death_message(self):
        zombie = Zombie(self.srv, 8000, pos=(1.0, 64.0, 0.0))
        seen = []
        self.subscribe(PlayerDeathEvent, seen.append)
        self.sess.health = 2.0
        self.sess.damage(5.0, attacker=zombie)
        self.assertIn("slain by zombie", seen[0].death_message)


class TestMobDamage(unittest.TestCase):
    def setUp(self):
        self.srv = MagicMock()
        self.srv.playing.return_value = []
        self.zombie = Zombie(self.srv, 900, pos=(0.0, 64.0, 0.0))
        self.sentinel = object()

    def tearDown(self):
        events.unregister_by_plugin(self.sentinel)

    def test_mob_damage_fires_the_damage_event(self):
        seen = []
        events.subscribe(EntityDamageEvent, seen.append, plugin=self.sentinel)
        self.assertTrue(self.zombie.damage(4.0))
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0].entity, self.zombie)
        self.assertAlmostEqual(seen[0].amount, 4.0)

    def test_mob_damage_cancellation_blocks_the_hit(self):
        events.subscribe(
            EntityDamageEvent, lambda ev: ev.cancel(), plugin=self.sentinel
        )
        self.assertFalse(self.zombie.damage(4.0))
        self.assertEqual(self.zombie.health, 20.0)

    def test_mob_damage_broadcasts_hurt_animation_and_attributes(self):
        self.zombie.damage(4.0)
        calls = self.srv.broadcast.call_args_list
        self.assertEqual(len(calls), 2)
        hurt = calls[0][0][0][0]
        attrs = calls[1][0][0][0]
        self.assertEqual(hurt[0], 27)  # PID_ACTOR_EVENT
        self.assertEqual(attrs[0], PID_UPDATE_ATTRIBUTES)
        self.assertIn(struct.pack("<f", 16.0), build_update_attributes(self.zombie))

    def test_mob_damage_is_gated_by_invulnerability_frames(self):
        self.zombie.damage(4.0)
        self.assertFalse(self.zombie.damage(4.0))
        self.assertEqual(self.zombie.health, 16.0)


class TestAttackFeedback(unittest.TestCase):
    def setUp(self):
        self.srv = MagicMock()
        self.srv.next_rid = 1
        self.srv.key = (MagicMock(), MagicMock())
        self.srv.entity_mgr = MagicMock()

    def make_session(self):
        sess = Session(self.srv, ("127.0.0.1", 19132), 1400, 100)
        sess.send_packet = MagicMock()
        sess.send_packets = MagicMock()
        sess.teleport = MagicMock()
        sess.broadcast_arm_swing = MagicMock()
        return sess

    def test_successful_attack_swings_the_attacker_arm(self):
        attacker = self.make_session()
        target = self.make_session()
        attacker._set_feet((0.0, 64.0, 0.0))
        target._set_feet((2.0, 64.0, 0.0))
        self.srv.playing.return_value = [attacker, target]

        player_pos = (0.0, 64.0 + NETWORK_EYE_OFFSET, 0.0)
        result = Server.handle_entity_attack(
            self.srv, attacker, target.rid, player_pos, (0.0, 64.9, 2.0)
        )
        self.assertTrue(result)
        attacker.broadcast_arm_swing.assert_called_once()
        self.assertEqual(target.health, 19.0)

    def test_out_of_range_attack_is_rejected(self):
        attacker = self.make_session()
        target = self.make_session()
        attacker._set_feet((0.0, 64.0, 0.0))
        target._set_feet((40.0, 64.0, 0.0))
        self.srv.playing.return_value = [attacker, target]

        player_pos = (0.0, 64.0 + NETWORK_EYE_OFFSET, 0.0)
        result = Server.handle_entity_attack(
            self.srv, attacker, target.rid, player_pos, (0.0, 64.9, 40.0)
        )
        self.assertFalse(result)
        attacker.broadcast_arm_swing.assert_not_called()
        self.assertEqual(target.health, 20.0)


if __name__ == "__main__":
    unittest.main()
