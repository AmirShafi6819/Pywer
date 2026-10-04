"""Regression tests for the packet-dispatch gaps closed in PR-5.

Every case here covers something that was previously unreachable, silently taken from a
server-wide default instead of the session, or an event class that was defined and never
dispatched anywhere.
"""

import struct
import unittest
from unittest.mock import MagicMock, patch

from pywer import config
from pywer.entity.item import ItemEntity
from pywer.entity.manager import EntityManager
from pywer.entity.projectile import Arrow
from pywer.event import (
    BlockInteractEvent,
    EntityDespawnEvent,
    EntitySpawnEvent,
    PlayerDropItemEvent,
    PlayerInteractEvent,
    ProjectileHitEvent,
)
from pywer.event import manager as events
from pywer.packets.abilities import (
    ABILITY_ALLOW_FLIGHT,
    ABILITY_FLYING,
    ABILITY_NO_CLIP,
    ability_bits,
)
from pywer.packets.spawn import build_add_player
from pywer.packets.start_game import build_start_game
from pywer.player.inventory import ITEM_AIR
from pywer.player.inventory_manager import InventoryError, InventoryManager
from pywer.player.session import Session
from pywer.protocol.flags import (
    BA_CONTINUE_DESTROY_BLOCK,
    BA_PREDICT_DESTROY_BLOCK,
    BA_START_BREAK,
    F_START_FLYING,
)
from pywer.protocol.inventory import WINDOW_WORKBENCH
from pywer.protocol.packet_ids import (
    PID_PACK_RESPONSE,
    PID_START_GAME,
    PID_UPDATE_ABILITIES,
)
from pywer.protocol.transaction import (
    ACTION_CLICK_AIR,
    ACTION_CLICK_BLOCK,
    read_block_pos,
)
from pywer.util.serializer import ByteReader, ByteWriter
from pywer.world.blocks import ITEM_TO_KEY, item_key_for_id

# i64 unique_id, u8 command perm, u8 player perm, u8 layer count, u16le layer id
ABILITIES_BITS_OFFSET = 13
# AbilitiesData is written raw into AddPlayerPacket: i64 + 3*u8 + u16 + 2*u32 + 2*float
ABILITIES_PAYLOAD_LEN = 29


def abilities_bits(payload):
    """set_abilities of the base layer inside an AbilitiesData payload."""
    return struct.unpack_from("<I", payload, ABILITIES_BITS_OFFSET)[0]


def decode_add_player(data):
    """(gamemode, ability bits) out of an AddPlayerPacket body."""
    r = ByteReader(data)
    r.read_uuid()
    r.read_string()
    r.read_varuint64()
    r.read_string()
    for _ in range(6):  # feet vec3 + motion vec3
        r.read_float()
    for _ in range(3):  # pitch, yaw, head yaw
        r.read_float()
    r.read_varint32()  # held item
    gamemode = r.read_varint32()
    for _ in range(r.read_varuint32()):  # metadata entries: (key, type, value)
        r.read_varuint32()
        typ = r.read_varuint32()
        if typ == 7:
            r.read_varint64()
        elif typ == 3:
            r.read_float()
        elif typ == 4:
            r.read_string()
        else:
            raise AssertionError("unexpected metadata type %d" % typ)
    r.read_varuint32()  # synced properties
    r.read_varuint32()
    return gamemode, abilities_bits(r.read_bytes(ABILITIES_PAYLOAD_LEN))


def player_action_body(rid, action, pos, face):
    w = ByteWriter()
    w.write_varuint64(rid)
    w.write_varint32(action)
    w.write_varint32(pos[0]).write_varuint32(pos[1]).write_varint32(pos[2])
    w.write_varint32(0).write_varuint32(0).write_varint32(0)  # result position
    w.write_varint32(face)
    return w.get()


def auth_input_body(flags, pos=(0.0, 65.62, 0.0)):
    """PlayerAuthInputPacket with no optional tails (no item interaction, no block actions)."""
    w = ByteWriter()
    w.write_float(0.0)  # pitch
    w.write_float(0.0)  # yaw
    w.write_float(pos[0]).write_float(pos[1]).write_float(pos[2])
    w.write_float(0.0)  # move_x
    w.write_float(0.0)  # move_z
    w.write_float(0.0)  # head_yaw
    w.write_varuint64(flags)  # flags: read as varuint(70), same LEB128 encoding
    w.write_varuint32(0)  # input mode
    w.write_varuint32(0)  # play mode
    w.write_varuint32(0)  # interaction mode
    w.write_float(0.0).write_float(0.0)  # interact rot
    w.write_varuint64(1)  # tick
    w.write_float(0.0).write_float(0.0).write_float(0.0)  # delta
    return w.get()


def use_item_tx(action, pos=(10, 64, 10), face=1):
    return {
        "action": action,
        "trigger": 0,
        "pos": pos,
        "face": face,
        "hotbar": 0,
        "item": {"id": 1},
        "player_pos": (0.0, 65.62, 0.0),
        "click_pos": (0.0, 0.0, 0.0),
        "block_runtime_id": 0,
        "prediction": 0,
        "cooldown": 0,
    }


class DispatchCase(unittest.TestCase):
    def setUp(self):
        self._plugin = object()

    def tearDown(self):
        events.unregister_by_plugin(self._plugin)

    def watch(self, event_cls, cancel=False):
        """Subscribe a handler that records every dispatch, optionally cancelling."""
        seen = []

        def handler(ev):
            seen.append(ev)
            if cancel:
                ev.cancel()

        events.subscribe(event_cls, handler, plugin=self._plugin)
        return seen

    def make_session(self):
        srv = MagicMock()
        srv.next_rid = 1
        srv.next_window_id.return_value = 5
        srv.container_id.return_value = 5
        srv.key = (MagicMock(), MagicMock())
        srv.chests = {}
        srv.playing.return_value = []
        sess = Session(srv, ("127.0.0.1", 19132), 1400, 100)
        sess.send_packet = MagicMock()
        sess.send_packets = MagicMock()
        sess.handle_movement = MagicMock()
        sess.stream_chunks = MagicMock()
        sess.sync_inventory = MagicMock()
        return sess

    def abilities_packets(self, sess):
        return [
            args[1]
            for (args, _kwargs) in sess.send_packet.call_args_list
            if args[0] == PID_UPDATE_ABILITIES
        ]


class TestPerSessionAbilities(DispatchCase):
    def test_survival_has_no_flight_by_default(self):
        bits = ability_bits(gamemode=0)
        self.assertFalse(bits & (1 << ABILITY_ALLOW_FLIGHT))
        self.assertFalse(bits & (1 << ABILITY_NO_CLIP))

    def test_creative_has_flight_and_noclip_by_default(self):
        bits = ability_bits(gamemode=1)
        self.assertTrue(bits & (1 << ABILITY_ALLOW_FLIGHT))
        self.assertTrue(bits & (1 << ABILITY_NO_CLIP))

    def test_allow_flight_is_a_per_session_value(self):
        # a survival player whose save says may-fly keeps may-fly, and gains no noclip
        bits = ability_bits(gamemode=0, allow_flight=True)
        self.assertTrue(bits & (1 << ABILITY_ALLOW_FLIGHT))
        self.assertFalse(bits & (1 << ABILITY_NO_CLIP))
        # a creative player whose save says it may not fly loses may-fly but keeps noclip
        bits = ability_bits(gamemode=1, allow_flight=False)
        self.assertFalse(bits & (1 << ABILITY_ALLOW_FLIGHT))
        self.assertTrue(bits & (1 << ABILITY_NO_CLIP))

    def test_flying_bit_follows_the_session(self):
        self.assertFalse(ability_bits(gamemode=0, flying=False) & (1 << ABILITY_FLYING))
        self.assertTrue(ability_bits(gamemode=0, flying=True) & (1 << ABILITY_FLYING))

    def test_update_abilities_reads_the_session_not_the_config(self):
        sess = self.make_session()
        sess.gamemode = 1
        sess.flying = True
        sess.allow_flight = False
        sess.sync_abilities()

        packets = self.abilities_packets(sess)
        self.assertEqual(len(packets), 1)
        bits = abilities_bits(packets[0])
        self.assertTrue(bits & (1 << ABILITY_FLYING))
        self.assertTrue(bits & (1 << ABILITY_NO_CLIP))
        self.assertFalse(bits & (1 << ABILITY_ALLOW_FLIGHT))

    def test_apply_dict_clamps_an_undefined_gamemode(self):
        sess = self.make_session()
        sess.apply_dict({"gamemode": 99})
        self.assertIn(sess.gamemode, config.VALID_GAMEMODES)
        sess.apply_dict({"gamemode": 1})
        self.assertEqual(sess.gamemode, 1)

    def test_add_player_carries_the_session_gamemode(self):
        sess = self.make_session()
        sess.gamemode = 1
        sess.flying = True
        sess.allow_flight = True
        gamemode, bits = decode_add_player(build_add_player(sess))
        self.assertEqual(gamemode, 1)
        self.assertTrue(bits & (1 << ABILITY_FLYING))
        self.assertTrue(bits & (1 << ABILITY_ALLOW_FLIGHT))

    def test_add_player_never_writes_an_undefined_gamemode(self):
        sess = self.make_session()
        sess.gamemode = 99
        gamemode, _bits = decode_add_player(build_add_player(sess))
        self.assertEqual(gamemode, 0)

    def test_restore_gamemode_handles_old_and_corrupt_saves(self):
        sess = self.make_session()

        # a world written before allow_flight was part of the save format
        sess.restore_gamemode({"gamemode": 1})
        self.assertEqual(sess.gamemode, 1)
        self.assertTrue(sess.allow_flight)

        # gamemode present: allow_flight is whatever the save says
        sess.restore_gamemode({"gamemode": 1, "allow_flight": False})
        self.assertFalse(sess.allow_flight)

        # values the protocol does not define, and values that are not even integers
        sess.restore_gamemode({"gamemode": 99, "allow_flight": True})
        self.assertIn(sess.gamemode, config.VALID_GAMEMODES)
        sess.restore_gamemode({"gamemode": "creative"})
        self.assertIn(sess.gamemode, config.VALID_GAMEMODES)

        # no save at all, or one that is not a mapping
        sess.restore_gamemode(None)
        self.assertIn(sess.gamemode, config.VALID_GAMEMODES)
        sess.restore_gamemode("not a mapping")
        self.assertIn(sess.gamemode, config.VALID_GAMEMODES)

    def test_apply_dict_still_restores_allow_flight(self):
        sess = self.make_session()
        sess.apply_dict({"gamemode": 1, "allow_flight": False})
        self.assertEqual(sess.gamemode, 1)
        self.assertFalse(sess.allow_flight)

    def test_start_game_announces_the_restored_gamemode(self):
        """StartGame goes out before the rest of the save - it must not contradict it."""
        sess = self.make_session()
        sess.srv.player_storage = {sess.uuid: {"gamemode": 1, "allow_flight": True}}

        w = ByteWriter()
        w.write_u8(4)  # COMPLETED
        w.write_u16_le(0)  # no resource packs
        sess.on_packet(PID_PACK_RESPONSE, w.get())

        start_game = [
            args[1]
            for (args, _kwargs) in sess.send_packet.call_args_list
            if args[0] == PID_START_GAME
        ]
        self.assertEqual(len(start_game), 1)
        r = ByteReader(start_game[0])
        r.read_varint64()  # actorUniqueId
        r.read_varuint64()  # actorRuntimeId
        self.assertEqual(r.read_varint32(), 1)  # player gamemode
        self.assertEqual(sess.gamemode, 1)
        self.assertTrue(sess.allow_flight)

    def test_start_game_default_still_matches_the_config(self):
        r = ByteReader(build_start_game(7))
        r.read_varint64()
        r.read_varuint64()
        self.assertEqual(r.read_varint32(), config.GAMEMODE)

    def test_start_game_never_writes_an_undefined_gamemode(self):
        """Both gamemode fields fall back to survival, so a typo changes nothing on the wire."""
        with patch.object(config, "GAMEMODE", 0):
            clean = build_start_game(7)
        with patch.object(config, "GAMEMODE", 99):
            self.assertEqual(build_start_game(7), clean)

    def test_starting_flight_resends_abilities_once(self):
        sess = self.make_session()
        sess.allow_flight = True
        sess.handle_auth_input(auth_input_body(1 << F_START_FLYING))
        self.assertTrue(sess.flying)
        self.assertEqual(len(self.abilities_packets(sess)), 1)
        bits = abilities_bits(self.abilities_packets(sess)[0])
        self.assertTrue(bits & (1 << ABILITY_FLYING))

        # the flag never changes, so neither does the ability - no packet per input tick
        sess.handle_auth_input(auth_input_body(1 << F_START_FLYING))
        self.assertEqual(len(self.abilities_packets(sess)), 1)


class TestPlayerInteractEvent(DispatchCase):
    def test_both_transports_report_one_click_once(self):
        sess = self.make_session()
        sess.try_place_block = MagicMock()
        seen = self.watch(PlayerInteractEvent)

        tx = use_item_tx(ACTION_CLICK_BLOCK)
        self.assertTrue(sess.handle_item_use(tx, "auth_input"))
        self.assertTrue(sess.handle_item_use(dict(tx), "transaction"))

        self.assertEqual(len(seen), 1)
        self.assertEqual(sess.try_place_block.call_count, 1)

    def test_two_real_clicks_from_one_transport_are_both_dispatched(self):
        sess = self.make_session()
        sess.try_place_block = MagicMock()
        seen = self.watch(PlayerInteractEvent)

        tx = use_item_tx(ACTION_CLICK_BLOCK)
        sess.handle_item_use(tx, "auth_input")
        sess.handle_item_use(dict(tx), "auth_input")

        self.assertEqual(len(seen), 2)
        self.assertEqual(sess.try_place_block.call_count, 2)

    def test_two_clicks_arriving_in_any_interleaving_are_both_dispatched(self):
        # Both transports may report the same click, so four reports can arrive in any
        # order. Deduplication has to swallow exactly two of them - the naive
        # "the pair is complete now, forget the key" rule drops the second click when
        # one transport's pair arrives ahead of the other's, and dispatches it twice
        # when one transport's two reports arrive as a block.
        tx = use_item_tx(ACTION_CLICK_AIR, pos=(0, 0, 0), face=0)
        interleavings = (
            ("auth_input", "transaction", "auth_input", "transaction"),
            ("auth_input", "transaction", "transaction", "auth_input"),
            ("transaction", "auth_input", "transaction", "auth_input"),
            ("auth_input", "auth_input", "transaction", "transaction"),
            ("transaction", "transaction", "auth_input", "auth_input"),
        )
        for order in interleavings:
            with self.subTest(order=order):
                sess = self.make_session()
                seen = self.watch(PlayerInteractEvent)
                for source in order:
                    sess.handle_item_use(dict(tx), source)

                self.assertEqual(len(seen), 2)

    def test_a_click_reported_only_by_the_other_transport_is_not_swallowed(self):
        # The reported defect: click 1 is reported by both transports and click 2 only
        # by the other one, so the still-armed key of click 1 deduplicates click 2 away.
        tx = use_item_tx(ACTION_CLICK_AIR, pos=(0, 0, 0), face=0)
        sequences = (
            ("auth_input", "transaction", "transaction"),
            ("transaction", "auth_input", "auth_input"),
            ("transaction", "auth_input", "transaction"),
            ("auth_input", "transaction", "auth_input"),
        )
        for order in sequences:
            with self.subTest(order=order):
                sess = self.make_session()
                seen = self.watch(PlayerInteractEvent)
                for source in order:
                    sess.handle_item_use(dict(tx), source)

                self.assertEqual(len(seen), 2)

    def test_interact_event_carries_the_held_item_not_the_client_claim(self):
        sess = self.make_session()
        seen = self.watch(PlayerInteractEvent)
        sess.inventory[sess.selected_slot] = (1, 3, 0)

        tx = use_item_tx(ACTION_CLICK_BLOCK)
        tx["item"] = {"id": 9999, "count": 64, "meta": 0}
        sess.handle_item_use(tx, "transaction")

        self.assertEqual(seen[0].item, (1, 3, 0))
        self.assertNotIsInstance(seen[0].item, dict)

    def test_empty_hand_reports_the_air_tuple(self):
        sess = self.make_session()
        seen = self.watch(PlayerInteractEvent)

        sess.handle_item_use(use_item_tx(ACTION_CLICK_AIR, pos=(0, 0, 0)), "transaction")

        self.assertEqual(seen[0].item, ITEM_AIR)

    def test_cancelled_interact_never_reaches_placement(self):
        sess = self.make_session()
        sess.try_place_block = MagicMock()
        self.watch(PlayerInteractEvent, cancel=True)

        self.assertFalse(sess.handle_item_use(use_item_tx(ACTION_CLICK_BLOCK), "transaction"))
        self.assertFalse(sess.try_place_block.called)

    def test_air_use_reports_no_block_position(self):
        sess = self.make_session()
        seen = self.watch(PlayerInteractEvent)

        sess.handle_item_use(use_item_tx(ACTION_CLICK_AIR, pos=(0, 0, 0), face=0), "transaction")

        self.assertEqual(len(seen), 1)
        self.assertIsNone(seen[0].block_pos)
        self.assertEqual(seen[0].action, ACTION_CLICK_AIR)

    def test_block_click_reports_the_clicked_position(self):
        sess = self.make_session()
        seen = self.watch(PlayerInteractEvent)

        sess.handle_item_use(use_item_tx(ACTION_CLICK_BLOCK), "auth_input")

        self.assertEqual(seen[0].block_pos, (10, 64, 10))
        self.assertEqual(seen[0].face, 1)


class TestLegacyPlayerAction(DispatchCase):
    def test_continue_break_reaches_the_break_timer(self):
        sess = self.make_session()
        sess.continue_break = MagicMock(return_value=True)
        sess.handle_player_action(
            player_action_body(sess.rid, BA_CONTINUE_DESTROY_BLOCK, (10, 64, 10), 1)
        )
        sess.continue_break.assert_called_once_with((10, 64, 10), 1)

    def test_start_break_still_starts_a_break(self):
        sess = self.make_session()
        sess.start_break = MagicMock()
        sess.handle_player_action(player_action_body(sess.rid, BA_START_BREAK, (10, 64, 10), 1))
        sess.start_break.assert_called_once_with((10, 64, 10), 1)

    def test_start_break_below_y_zero_reaches_the_handler(self):
        # Y travels as an unsigned varint, so without sign extension the decoder turns
        # -1 into 4294967295 and every block below y=0 is rejected as out of world.
        sess = self.make_session()
        sess.start_break = MagicMock()
        sess.handle_player_action(
            player_action_body(sess.rid, BA_START_BREAK, (10, -1, 10), 1)
        )
        sess.start_break.assert_called_once_with((10, -1, 10), 1)

    def test_read_block_pos_sign_extends_unsigned_y(self):
        w = ByteWriter()
        w.write_varint32(-3).write_varuint32(-1 & 0xFFFFFFFF).write_varint32(7)

        self.assertEqual(read_block_pos(ByteReader(w.get())), (-3, -1, 7))

    def test_predict_destroy_is_reported_but_never_honoured(self):
        sess = self.make_session()
        sess.break_target = (10, 64, 10)
        sess.break_progress = 0.4
        sess.start_break = MagicMock()
        sess.stop_break = MagicMock()
        sess.handle_player_action(
            player_action_body(sess.rid, BA_PREDICT_DESTROY_BLOCK, (10, 64, 10), 1)
        )
        self.assertEqual(sess.break_target, (10, 64, 10))
        sess.start_break.assert_not_called()
        sess.stop_break.assert_not_called()

    def test_auth_input_actions_win_and_disable_the_fallback(self):
        sess = self.make_session()
        sess.seen_block_actions = True
        sess.start_break = MagicMock()
        sess.handle_player_action(player_action_body(sess.rid, BA_START_BREAK, (10, 64, 10), 1))
        sess.start_break.assert_not_called()


class TestBlockInteractEvent(DispatchCase):
    def test_cancelled_chest_click_opens_nothing(self):
        sess = self.make_session()
        self.watch(BlockInteractEvent, cancel=True)

        self.assertFalse(sess.open_chest((12, 64, 12)))
        self.assertFalse(sess.open_window)
        self.assertNotIn((12, 64, 12), sess.srv.chests)
        sess.send_packet.assert_not_called()

    def test_chest_click_still_opens_without_a_handler(self):
        sess = self.make_session()
        self.assertTrue(sess.open_chest((12, 64, 12)))
        self.assertTrue(sess.open_window)
        self.assertIn((12, 64, 12), sess.srv.chests)

    def test_cancelled_crafting_table_click_opens_nothing(self):
        sess = self.make_session()
        self.watch(BlockInteractEvent, cancel=True)

        self.assertFalse(sess.open_crafting_table((10, 64, 10)))
        self.assertFalse(sess.open_window)
        sess.send_packet.assert_not_called()


class TestPlayerDropItemEvent(DispatchCase):
    def setUp(self):
        super().setUp()
        self.legacy_id = next(k for k in ITEM_TO_KEY if item_key_for_id(k))
        self.lst = [(self.legacy_id, 5, 0)]
        self.srv = MagicMock()
        self.srv.drop_item.side_effect = lambda pos, key, count=1: count
        self.sess = MagicMock()
        self.sess.srv = self.srv
        self.sess.feet.return_value = (0.0, 64.0, 0.0)
        self.sess.resolve_slot.return_value = (0, self.lst, 0)

    def test_cancelled_drop_leaves_the_slot_untouched(self):
        seen = self.watch(PlayerDropItemEvent, cancel=True)
        with self.assertRaises(InventoryError):
            InventoryManager(self.sess)._drop(2, (0, 0))

        self.assertEqual(len(seen), 1)
        self.assertEqual(self.lst[0], (self.legacy_id, 5, 0))
        self.srv.drop_item.assert_not_called()

    def test_drop_still_works_without_a_handler(self):
        changed = InventoryManager(self.sess)._drop(2, (0, 0))

        self.assertEqual(changed, {(id(self.lst), 0)})
        self.assertEqual(self.lst[0][1], 3)
        self.srv.drop_item.assert_called_once()

    def test_only_what_reached_the_world_is_deducted(self):
        self.srv.drop_item.side_effect = None
        self.srv.drop_item.return_value = 1

        changed = InventoryManager(self.sess)._drop(2, (0, 0))

        self.assertEqual(changed, {(id(self.lst), 0)})
        self.assertEqual(self.lst[0], (self.legacy_id, 4, 0))


class TestEntityLifecycleEvents(DispatchCase):
    def make_manager(self):
        srv = MagicMock()
        srv.next_rid = 1000
        srv.playing.return_value = []
        return EntityManager(srv)

    def test_cancelled_spawn_registers_and_indexes_nothing(self):
        mgr = self.make_manager()
        self.watch(EntitySpawnEvent, cancel=True)

        spawned = mgr.spawn(ItemEntity, "stone", 1, pos=(0.0, 64.0, 0.0))

        self.assertIsNone(spawned)
        self.assertEqual(mgr.entities, {})
        self.assertEqual(mgr.chunk_index, {})

    def test_spawn_still_works_without_a_handler(self):
        mgr = self.make_manager()
        item = mgr.spawn(ItemEntity, "stone", 1, pos=(0.0, 64.0, 0.0))
        self.assertIsNotNone(item)
        self.assertIn(item.rid, mgr.entities)

    def test_despawn_event_sees_an_entity_already_out_of_the_world(self):
        mgr = self.make_manager()
        item = mgr.spawn(ItemEntity, "stone", 1, pos=(0.0, 64.0, 0.0))
        seen = self.watch(EntityDespawnEvent)

        mgr.remove(item.rid)

        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0].entity, item)
        self.assertNotIn(item.rid, mgr.entities)
        self.assertTrue(item.dead)

    def test_cancelled_item_spawn_makes_drop_item_report_failure(self):
        mgr = self.make_manager()
        self.watch(EntitySpawnEvent, cancel=True)

        self.assertFalse(mgr.drop_item((0.0, 64.0, 0.0), "stone", 1))
        self.assertEqual(mgr.entities, {})

    def test_vetoed_second_stack_reports_only_the_stacks_that_spawned(self):
        mgr = self.make_manager()
        events.subscribe(
            EntitySpawnEvent,
            lambda ev: ev.cancel() if mgr.entities else None,
            plugin=self._plugin,
        )

        placed = mgr.drop_item((0.0, 64.0, 0.0), "stone", 100)

        self.assertEqual(placed, 64)
        stacks = [e for e in mgr.entities.values() if isinstance(e, ItemEntity)]
        self.assertEqual(sum(e.count for e in stacks), 64)


class TestCraftingCloseAccounting(DispatchCase):
    def test_results_the_world_refuses_stay_in_the_container(self):
        sess = self.make_session()
        sess.open_window = True
        sess.open_window_type = WINDOW_WORKBENCH
        c3 = sess.containers.complex.get("crafting3x3")
        c3.items[0] = (1, 64, 0)
        for i in range(len(sess.inventory)):
            sess.inventory[i] = (1, 64, 0)
        sess.srv.drop_item.return_value = 40

        sess.close_main_inventory()

        self.assertEqual(c3.items[0], (1, 24, 0))

    def test_results_are_cleared_once_the_world_takes_them(self):
        sess = self.make_session()
        sess.open_window = True
        sess.open_window_type = WINDOW_WORKBENCH
        c3 = sess.containers.complex.get("crafting3x3")
        c3.items[0] = (1, 10, 0)
        sess.srv.drop_item.return_value = 10

        sess.close_main_inventory()

        self.assertEqual(c3.items[0], ITEM_AIR)


class TestProjectileHitEvent(DispatchCase):
    def make_projectile(self):
        srv = MagicMock()
        srv.next_rid = 2000
        return Arrow(srv, 2000, pos=(0.0, 64.0, 0.0), motion=(1.0, 0.0, 0.0))

    def test_block_hit_fires_before_the_arrow_sticks(self):
        proj = self.make_projectile()
        seen = self.watch(ProjectileHitEvent)

        with patch(
            "pywer.entity.physics.check_projectile_collisions",
            return_value=("block", (5, 64, 5), (5.0, 64.0, 5.0)),
        ):
            proj.tick(0.0, 0.05, lambda _x, _y, _z: False)

        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].hit_type, "block")
        self.assertTrue(proj.in_ground)
        self.assertEqual(proj.pos, (5.0, 64.0, 5.0))
        self.assertFalse(proj.dead)

    def test_cancelled_hit_consumes_the_projectile_without_applying_it(self):
        proj = self.make_projectile()
        self.watch(ProjectileHitEvent, cancel=True)
        target = MagicMock()

        with patch(
            "pywer.entity.physics.check_projectile_collisions",
            return_value=("entity", target, (1.0, 64.0, 1.0)),
        ):
            proj.tick(0.0, 0.05, lambda _x, _y, _z: False)

        self.assertTrue(proj.dead)
        self.assertFalse(proj.in_ground)
        target.damage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
