import unittest
from unittest.mock import MagicMock
from pywer.player.containers import (
    ContainerRegistry,
    UI_CREATED_OUTPUT_SLOT,
    UI_CRAFTING3X3,
    UI_CRAFTING2X2,
    UI_CURSOR,
)


class TestContainerMapping(unittest.TestCase):
    def test_complex_slot_mappings(self):
        sess = MagicMock()
        sess.inventory = [(0, 0, 0)] * 36
        reg = ContainerRegistry(sess)

        # Test cursor (slot 0)
        hit_cursor = reg.complex_for_slot(UI_CURSOR)
        self.assertIsNotNone(hit_cursor)
        entry_cursor, core_cursor = hit_cursor
        self.assertEqual(core_cursor, 0)
        self.assertIs(entry_cursor, reg.complex["cursor"])

        # Test created_output (slot 50)
        hit_output = reg.complex_for_slot(UI_CREATED_OUTPUT_SLOT)
        self.assertIsNotNone(hit_output)
        entry_output, core_output = hit_output
        self.assertEqual(core_output, 0)
        self.assertIs(entry_output, reg.complex["created_output"])
        self.assertEqual(len(entry_output.items), 1)

        # Test crafting2x2 (slots 28-31)
        for net_slot, expected_core in UI_CRAFTING2X2.items():
            hit2x2 = reg.complex_for_slot(net_slot)
            self.assertIsNotNone(hit2x2)
            entry2x2, core2x2 = hit2x2
            self.assertEqual(core2x2, expected_core)
            self.assertIs(entry2x2, reg.complex["crafting2x2"])

        # Test crafting3x3 (slots 32-40)
        self.assertEqual(len(UI_CRAFTING3X3), 9)
        for net_slot, expected_core in UI_CRAFTING3X3.items():
            hit3x3 = reg.complex_for_slot(net_slot)
            self.assertIsNotNone(hit3x3)
            entry3x3, core3x3 = hit3x3
            self.assertEqual(core3x3, expected_core)
            self.assertIs(entry3x3, reg.complex["crafting3x3"])
        self.assertEqual(len(reg.complex["crafting3x3"].items), 9)


if __name__ == "__main__":
    unittest.main()
