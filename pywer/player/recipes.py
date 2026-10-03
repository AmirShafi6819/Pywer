"""Core survival crafting recipes and pattern matching engine."""

ITEM_AIR = (0, 0, 0)

# Common block & item IDs
ID_LOG = 17
ID_LOG2 = 162
ID_PLANKS = 5
ID_CRAFTING_TABLE = 58
ID_STICK = 280
ID_TORCH = 50
ID_COAL = 263
ID_WOODEN_PICKAXE = 270
ID_WOODEN_SWORD = 268
ID_WOODEN_AXE = 271
ID_WOODEN_SHOVEL = 269
ID_CHEST = 54


def _trim_grid(grid, width):
    """Normalize a 2x2 or 3x3 grid to minimal bounding box of item IDs."""
    height = len(grid) // width
    items_2d = [[grid[r * width + c][0] for c in range(width)] for r in range(height)]
    min_r, max_r = height, -1
    min_c, max_c = width, -1
    for r in range(height):
        for c in range(width):
            if items_2d[r][c] != 0:
                min_r = min(min_r, r)
                max_r = max(max_r, r)
                min_c = min(min_c, c)
                max_c = max(max_c, c)
    if max_r == -1:
        return []
    return [
        tuple(items_2d[r][c] for c in range(min_c, max_c + 1))
        for r in range(min_r, max_r + 1)
    ]


def match_recipe(grid):
    """Match items in 2x2 or 3x3 grid against known recipes. Returns (item_id, count, meta) or None."""
    non_air = [it for it in grid if it[0] != 0]
    if not non_air:
        return None

    # 1. Shapeless single-log to 4 planks
    if len(non_air) == 1 and non_air[0][0] in (ID_LOG, ID_LOG2):
        return (ID_PLANKS, 4, non_air[0][2])

    width = 2 if len(grid) <= 4 else 3
    pattern = _trim_grid(grid, width)

    # 2. 4 Planks in 2x2 -> Crafting Table
    if pattern == [(ID_PLANKS, ID_PLANKS), (ID_PLANKS, ID_PLANKS)]:
        return (ID_CRAFTING_TABLE, 1, 0)

    # 3. 2 Planks vertical -> 4 Sticks
    if pattern == [(ID_PLANKS,), (ID_PLANKS,)]:
        return (ID_STICK, 4, 0)

    # 4. 1 Coal/Charcoal + 1 Stick -> 4 Torches
    if pattern == [(ID_COAL,), (ID_STICK,)]:
        return (ID_TORCH, 4, 0)

    # 5. 8 Planks in ring -> 1 Chest
    if pattern == [
        (ID_PLANKS, ID_PLANKS, ID_PLANKS),
        (ID_PLANKS, 0, ID_PLANKS),
        (ID_PLANKS, ID_PLANKS, ID_PLANKS),
    ]:
        return (ID_CHEST, 1, 0)

    # 6. Wooden Pickaxe (3 planks top, 2 sticks middle column)
    if pattern == [
        (ID_PLANKS, ID_PLANKS, ID_PLANKS),
        (0, ID_STICK, 0),
        (0, ID_STICK, 0),
    ]:
        return (ID_WOODEN_PICKAXE, 1, 0)

    # 7. Wooden Sword (2 planks, 1 stick below)
    if pattern == [(ID_PLANKS,), (ID_PLANKS,), (ID_STICK,)]:
        return (ID_WOODEN_SWORD, 1, 0)

    # 8. Wooden Axe (3 planks corner, 2 sticks)
    if pattern in (
        [(ID_PLANKS, ID_PLANKS), (ID_PLANKS, ID_STICK), (0, ID_STICK)],
        [(ID_PLANKS, ID_PLANKS), (ID_STICK, ID_PLANKS), (ID_STICK, 0)],
    ):
        return (ID_WOODEN_AXE, 1, 0)

    # 9. Wooden Shovel (1 plank, 2 sticks below)
    if pattern == [(ID_PLANKS,), (ID_STICK,), (ID_STICK,)]:
        return (ID_WOODEN_SHOVEL, 1, 0)

    return None
