import unittest
from unittest.mock import MagicMock
from pywer.player.inventory_manager import (
    InventoryManager,
    InventoryError,
    ACTION_TAKE,
    ACTION_PLACE,
    ACTION_CONSUME,
    ACTION_CREATE_OUTPUT,
    ACTION_CREATIVE_CREATE,
)
from pywer.player.containers import (
    ContainerRegistry,
    UI_CREATED_OUTPUT_SLOT,
    CONTAINER_INVENTORY,
    CONTAINER_UI,
)
from pywer.player.prediction import PredictionTracker
from pywer.player.recipes import ID_LOG, ID_PLANKS

ITEM_AIR = (0, 0, 0)


class MockSession:
    def __init__(self, creative=False):
        self._creative = creative
        self.inventory = [ITEM_AIR] * 36
        self.next_stack_id = 1
        self.open_window = False
        self.open_window_id = None
        self.window_to_container = {}
        self.seen_slot_mappings = set()
        self.containers = ContainerRegistry(self)
        self.predictions = PredictionTracker(self)

    def gamemode_is_creative(self):
        return self._creative

    def canonical_container(self, cid):
        if cid == 60:  # UI_CREATED_OUTPUT
            return CONTAINER_UI
        if cid == 13:  # UI_CRAFTING_INPUT
            return CONTAINER_UI
        if cid in (28, 29, 12):  # UI_HOTBAR, UI_INVENTORY, UI_COMBINED
            return CONTAINER_INVENTORY
        return cid

    def resolve_slot(self, cid, slot):
        orig_cid = cid
        cid = self.canonical_container(cid)
        if orig_cid == 60 or cid == CONTAINER_UI:
            if orig_cid == 60 and slot == 0:
                slot = UI_CREATED_OUTPUT_SLOT
            hit = self.containers.complex_for_slot(slot)
            if hit is None:
                return None
            entry, core = hit
            return ("ui:%d" % slot, entry.items, core)
        cont = self.containers.get(cid)
        if cont is not None and 0 <= slot < len(cont):
            return (cid, cont, slot)
        return None


class TestInventoryActions(unittest.TestCase):
    def test_creative_create_action_allowed(self):
        sess = MockSession(creative=True)
        mgr = InventoryManager(sess)

        # Creative create: item_id 1 (stone), count 64
        act = (ACTION_CREATIVE_CREATE, 1, 64)
        touched = mgr.apply_request(1001, [act])
        output_item = sess.containers.complex["created_output"].items[0]
        self.assertEqual(output_item, (1, 64, 0))
        self.assertIn((id(sess.containers.complex["created_output"].items), 0), touched)

    def test_creative_create_action_rejected_in_survival(self):
        sess = MockSession(creative=False)
        mgr = InventoryManager(sess)

        act = (ACTION_CREATIVE_CREATE, 1, 64)
        with self.assertRaises(InventoryError):
            mgr.apply_request(1001, [act])
        output_item = sess.containers.complex["created_output"].items[0]
        self.assertEqual(output_item, ITEM_AIR)

    def test_prediction_tracker_empty_slot(self):
        sess = MockSession(creative=False)
        # Empty slot should match client stack id 0 or negative
        self.assertTrue(sess.predictions.matches_client_stack_id(CONTAINER_INVENTORY, 0, 0))
        self.assertTrue(sess.predictions.matches_client_stack_id(CONTAINER_INVENTORY, 0, -1))
        # But not positive
        self.assertFalse(sess.predictions.matches_client_stack_id(CONTAINER_INVENTORY, 0, 42))

    def test_crafting_recipe_and_consume(self):
        sess = MockSession(creative=False)
        mgr = InventoryManager(sess)

        # Put 1 oak log in 2x2 crafting grid slot 0 (UI net slot 28)
        craft2x2 = sess.containers.complex["crafting2x2"]
        craft2x2.items[0] = (ID_LOG, 1, 0)
        sess.predictions.track_item_stack(CONTAINER_UI, 28, craft2x2.items[0])

        # Transaction:
        # 1. ACTION_CONSUME 1 from UI slot 28
        # 2. ACTION_CREATE_OUTPUT
        # 3. ACTION_TAKE 4 planks from output (UI slot 50) to hotbar slot 0
        actions = [
            (ACTION_CONSUME, 1, (CONTAINER_UI, 28, 0)),
            (ACTION_CREATE_OUTPUT, 0),
            (ACTION_TAKE, 4, (CONTAINER_UI, UI_CREATED_OUTPUT_SLOT, 0), (CONTAINER_INVENTORY, 0, 0)),
        ]
        touched = mgr.apply_request(1002, actions)

        # Verify results: crafting slot empty, hotbar slot has 4 planks, output empty
        self.assertEqual(craft2x2.items[0], ITEM_AIR)
        self.assertEqual(sess.inventory[0], (ID_PLANKS, 4, 0))
        self.assertEqual(sess.containers.complex["created_output"].items[0], ITEM_AIR)


if __name__ == "__main__":
    unittest.main()
