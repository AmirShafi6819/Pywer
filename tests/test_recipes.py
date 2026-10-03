import unittest
from pywer.player.recipes import (
    match_recipe,
    ID_LOG,
    ID_PLANKS,
    ID_CRAFTING_TABLE,
    ID_STICK,
    ID_TORCH,
    ID_COAL,
    ID_WOODEN_PICKAXE,
    ID_WOODEN_SWORD,
    ID_WOODEN_AXE,
    ID_WOODEN_SHOVEL,
    ID_CHEST,
)

ITEM_AIR = (0, 0, 0)


class TestRecipes(unittest.TestCase):
    def test_log_to_planks(self):
        # 1 oak log (id 17) -> 4 oak planks (id 5)
        grid = [ITEM_AIR] * 4
        grid[0] = (ID_LOG, 1, 0)
        res = match_recipe(grid)
        self.assertIsNotNone(res)
        self.assertEqual(res, (ID_PLANKS, 4, 0))

    def test_log2_to_planks(self):
        # 1 acacia/dark oak log (id 162) -> 4 planks
        grid = [ITEM_AIR] * 4
        grid[2] = (162, 1, 1)
        res = match_recipe(grid)
        self.assertIsNotNone(res)
        self.assertEqual(res, (ID_PLANKS, 4, 1))

    def test_planks_to_crafting_table(self):
        # 4 planks -> 1 crafting table (id 58)
        grid = [(ID_PLANKS, 1, 0)] * 4
        res = match_recipe(grid)
        self.assertIsNotNone(res)
        self.assertEqual(res, (ID_CRAFTING_TABLE, 1, 0))

    def test_planks_to_sticks_2x2(self):
        # 2 vertical planks in 2x2 grid (slot 0 and 2) -> 4 sticks (id 280)
        grid = [ITEM_AIR] * 4
        grid[0] = (ID_PLANKS, 1, 0)
        grid[2] = (ID_PLANKS, 1, 0)
        res = match_recipe(grid)
        self.assertIsNotNone(res)
        self.assertEqual(res, (ID_STICK, 4, 0))

    def test_planks_to_sticks_3x3_offset(self):
        # 2 vertical planks in 3x3 grid (slot 4 and 7) -> 4 sticks
        grid = [ITEM_AIR] * 9
        grid[4] = (ID_PLANKS, 1, 0)
        grid[7] = (ID_PLANKS, 1, 0)
        res = match_recipe(grid)
        self.assertIsNotNone(res)
        self.assertEqual(res, (ID_STICK, 4, 0))

    def test_coal_and_stick_to_torches(self):
        # 1 coal + 1 stick below -> 4 torches
        grid = [ITEM_AIR] * 4
        grid[1] = (ID_COAL, 1, 0)
        grid[3] = (ID_STICK, 1, 0)
        res = match_recipe(grid)
        self.assertIsNotNone(res)
        self.assertEqual(res, (ID_TORCH, 4, 0))

    def test_planks_to_chest_3x3(self):
        # 8 planks in ring around empty center (slot 4 empty)
        grid = [(ID_PLANKS, 1, 0)] * 9
        grid[4] = ITEM_AIR
        res = match_recipe(grid)
        self.assertIsNotNone(res)
        self.assertEqual(res, (ID_CHEST, 1, 0))

    def test_wooden_tools(self):
        # Wooden pickaxe: row 0 all planks, slot 4 stick, slot 7 stick
        grid_pick = [ITEM_AIR] * 9
        grid_pick[0] = (ID_PLANKS, 1, 0)
        grid_pick[1] = (ID_PLANKS, 1, 0)
        grid_pick[2] = (ID_PLANKS, 1, 0)
        grid_pick[4] = (ID_STICK, 1, 0)
        grid_pick[7] = (ID_STICK, 1, 0)
        res = match_recipe(grid_pick)
        self.assertEqual(res, (ID_WOODEN_PICKAXE, 1, 0))

        # Wooden sword: slot 1 plank, slot 4 plank, slot 7 stick
        grid_sword = [ITEM_AIR] * 9
        grid_sword[1] = (ID_PLANKS, 1, 0)
        grid_sword[4] = (ID_PLANKS, 1, 0)
        grid_sword[7] = (ID_STICK, 1, 0)
        res = match_recipe(grid_sword)
        self.assertEqual(res, (ID_WOODEN_SWORD, 1, 0))

        # Wooden shovel: slot 1 plank, slot 4 stick, slot 7 stick
        grid_shovel = [ITEM_AIR] * 9
        grid_shovel[1] = (ID_PLANKS, 1, 0)
        grid_shovel[4] = (ID_STICK, 1, 0)
        grid_shovel[7] = (ID_STICK, 1, 0)
        res = match_recipe(grid_shovel)
        self.assertEqual(res, (ID_WOODEN_SHOVEL, 1, 0))

    def test_empty_and_invalid_grid(self):
        self.assertIsNone(match_recipe([ITEM_AIR] * 4))
        self.assertIsNone(match_recipe([ITEM_AIR] * 9))
        self.assertIsNone(match_recipe([(999, 1, 0), ITEM_AIR, ITEM_AIR, ITEM_AIR]))


if __name__ == "__main__":
    unittest.main()
