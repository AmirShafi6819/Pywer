# Inventory & Container System Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Bedrock inventory transaction handling to fully support crafting (2x2 grid and 3x3 workbench), creative item selection, and interactive block containers (Chests and Crafting Tables) without prediction errors or desync rollbacks.

**Architecture:** A modular recipe engine in `pywer.player.recipes` evaluates shapeless and shaped recipe patterns. `ContainerRegistry` in `pywer.player.containers` maps `created_output` and `crafting3x3` slots to Bedrock UI offsets. `InventoryManager` executes `ACTION_CONSUME`, `ACTION_CREATE_OUTPUT`, and `ACTION_CREATIVE_CREATE`. `Server` and `Session` intercept right-clicks on crafting tables and chests to manage interactive container windows and 27-slot chest storage.

**Tech Stack:** Python 3.10+, Bedrock Protocol 766 (v1.21.50), standard library `unittest`.

**Spec:** [`docs/superpowers/specs/2026-10-03-inventory-and-container-hardening-design.md`](file:///c:/Users/Mani/Desktop/Pywer/docs/superpowers/specs/2026-10-03-inventory-and-container-hardening-design.md)

## Global Constraints
- Target Bedrock protocol: 766 (v1.21.50).
- Pure standard library Python only (no external pip dependencies).
- Game simulation state (player locations, inventories, active sessions) remains strictly single-threaded on the main loop.
- No statement semicolons or un-expanded compound lines. All code must conform to PEP 8.
- 100% preservation of existing comments, network bitmasks, and endianness.

---

### Task 1: Core Recipe Matching Engine (`pywer.player.recipes`)

**Files:**
- Create: `pywer/player/recipes.py`
- Test: `tests/test_recipes.py`

**Interfaces:**
- Consumes: `ITEM_AIR = (0, 0, 0)`
- Produces:
  - `match_recipe(grid: list[tuple[int, int, int]]) -> tuple[int, int, int] | None`
  - Constants for core crafting recipes

- [ ] **Step 1: Write failing unit tests for `match_recipe`**

```python
# tests/test_recipes.py
import unittest
from pywer.player.recipes import match_recipe

ITEM_AIR = (0, 0, 0)

class TestRecipes(unittest.TestCase):
    def test_log_to_planks(self):
        # 1 oak log (id 17) -> 4 oak planks (id 5)
        grid = [ITEM_AIR] * 4
        grid[0] = (17, 1, 0)
        res = match_recipe(grid)
        self.assertIsNotNone(res)
        self.assertEqual(res, (5, 4, 0))

    def test_planks_to_crafting_table(self):
        # 4 planks -> 1 crafting table (id 58)
        grid = [(5, 1, 0)] * 4
        res = match_recipe(grid)
        self.assertIsNotNone(res)
        self.assertEqual(res, (58, 1, 0))

    def test_planks_to_sticks(self):
        # 2 vertical planks in 2x2 grid (slot 0 and 2) -> 4 sticks (id 280)
        grid = [ITEM_AIR] * 4
        grid[0] = (5, 1, 0)
        grid[2] = (5, 1, 0)
        res = match_recipe(grid)
        self.assertIsNotNone(res)
        self.assertEqual(res, (280, 4, 0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_recipes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.player.recipes'`

- [ ] **Step 3: Implement `pywer/player/recipes.py`**

```python
# pywer/player/recipes.py
"""Core survival crafting recipes and pattern matching engine."""

ITEM_AIR = (0, 0, 0)

# Common block & item IDs
ID_LOG = 17
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
    if len(non_air) == 1 and non_air[0][0] in (ID_LOG, 162):  # 17: Log, 162: Log2
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_recipes.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 1**

```bash
git add pywer/player/recipes.py tests/test_recipes.py
git commit -m "feat: add survival crafting recipe matching engine"
```

---

### Task 2: Complex UI Container Slot Mapping (`pywer.player.containers`)

**Files:**
- Modify: `pywer/player/containers.py`
- Test: `tests/test_container_mapping.py`

**Interfaces:**
- Consumes: `ComplexContainer`
- Produces:
  - `UI_CREATED_OUTPUT_SLOT = 50`
  - `UI_CRAFTING3X3` map
  - `ContainerRegistry.complex["created_output"]`
  - `ContainerRegistry.complex["crafting3x3"]`

- [ ] **Step 1: Write failing unit test for `created_output` and `crafting3x3` mapping**

```python
# tests/test_container_mapping.py
import unittest
from unittest.mock import MagicMock
from pywer.player.containers import ContainerRegistry, UI_CREATED_OUTPUT_SLOT, UI_CRAFTING3X3

class TestContainerMapping(unittest.TestCase):
    def test_complex_slot_mappings(self):
        sess = MagicMock()
        sess.inventory = [(0, 0, 0)] * 36
        reg = ContainerRegistry(sess)
        
        # Test created_output (slot 50)
        hit = reg.complex_for_slot(UI_CREATED_OUTPUT_SLOT)
        self.assertIsNotNone(hit)
        entry, core = hit
        self.assertEqual(core, 0)
        
        # Test crafting3x3 (slot 32)
        hit3x3 = reg.complex_for_slot(32)
        self.assertIsNotNone(hit3x3)
        entry3, core3 = hit3x3
        self.assertEqual(core3, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_container_mapping.py -v`
Expected: FAIL with `ImportError: cannot import name 'UI_CREATED_OUTPUT_SLOT' from 'pywer.player.containers'`

- [ ] **Step 3: Update `pywer/player/containers.py`**
  - Define `UI_CREATED_OUTPUT_SLOT = 50`.
  - Define `UI_CRAFTING3X3 = {32 + i: i for i in range(9)}`.
  - Add `"created_output": ComplexContainer({UI_CREATED_OUTPUT_SLOT: 0}, 1)` and `"crafting3x3": ComplexContainer(UI_CRAFTING3X3, 9)` to `ContainerRegistry.__init__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_container_mapping.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 2**

```bash
git add pywer/player/containers.py tests/test_container_mapping.py
git commit -m "feat: map created_output and crafting3x3 complex container slots"
```

---

### Task 3: Action Pipeline Expansion in `InventoryManager`

**Files:**
- Modify: `pywer/player/inventory_manager.py`
- Modify: `pywer/player/prediction.py`
- Test: `tests/test_inventory_actions.py`

**Interfaces:**
- Consumes: `match_recipe`, `created_output`, `session.gamemode_is_creative()`
- Produces:
  - Working `ACTION_CONSUME` (5)
  - Working `ACTION_CREATE_OUTPUT` (6)
  - Working `ACTION_CREATIVE_CREATE` (14)
  - Tolerant empty-slot prediction validation

- [ ] **Step 1: Write failing unit tests for actions 5, 6, and 14**

```python
# tests/test_inventory_actions.py
import unittest
from unittest.mock import MagicMock
from pywer.player.inventory_manager import (
    InventoryManager,
    ACTION_CONSUME,
    ACTION_CREATE_OUTPUT,
    ACTION_CREATIVE_CREATE,
)
from pywer.player.containers import ContainerRegistry, UI_CREATED_OUTPUT_SLOT
from pywer.player.prediction import PredictionTracker

class TestInventoryActions(unittest.TestCase):
    def test_creative_create_action(self):
        sess = MagicMock()
        sess.gamemode_is_creative.return_value = True
        sess.inventory = [(0, 0, 0)] * 36
        sess.containers = ContainerRegistry(sess)
        sess.predictions = PredictionTracker(sess)
        mgr = InventoryManager(sess)

        # Creative create: item_id 1 (stone), count 64
        act = (ACTION_CREATIVE_CREATE, 1, 64)
        touched = mgr.apply_request(1001, [act])
        output_item = sess.containers.complex["created_output"].items[0]
        self.assertEqual(output_item, (1, 64, 0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_inventory_actions.py -v`
Expected: FAIL with `ImportError: cannot import name 'ACTION_CREATE_OUTPUT'` or `unsupported action`

- [ ] **Step 3: Update `pywer/player/inventory_manager.py` and `pywer/player/prediction.py`**
  - Define `ACTION_CREATE_OUTPUT = 6` and `ACTION_CREATIVE_CREATE = 14`.
  - In `PredictionTracker.matches_client_stack_id(cid, slot, client_stack_id)`:
    - If `info is None` or `info.stack_id == 0`: allow `client_stack_id <= 0` (empty slot).
  - In `InventoryManager.apply_request`:
    - Handle `ACTION_CONSUME`: decrement count from source crafting slot.
    - Handle `ACTION_CREATE_OUTPUT`: evaluate active crafting grid with `match_recipe`, place result in `created_output.items[0]`.
    - Handle `ACTION_CREATIVE_CREATE`: check creative gamemode, place requested item in `created_output.items[0]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_inventory_actions.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 3**

```bash
git add pywer/player/inventory_manager.py pywer/player/prediction.py tests/test_inventory_actions.py
git commit -m "feat: implement crafting consume, output creation, and creative item generation"
```

---

### Task 4: Interactive Block Containers (Crafting Table & Chests)

**Files:**
- Modify: `pywer/server/server.py`
- Modify: `pywer/player/session.py`
- Test: `tests/test_block_containers.py`

**Interfaces:**
- Consumes: `Session.try_place_block`, `Server.chests`
- Produces:
  - `Session.open_crafting_table(pos)`
  - `Session.open_chest(pos)`
  - `Server.chests` persistence & destruction drop handling

- [ ] **Step 1: Write unit tests for opening workbench and chest**

```python
# tests/test_block_containers.py
import unittest
from unittest.mock import MagicMock
from pywer.player.session import Session

class TestBlockContainers(unittest.TestCase):
    def test_open_crafting_table(self):
        srv = MagicMock()
        srv.next_rid = 1
        srv.key = (MagicMock(), MagicMock())
        srv.next_window_id.return_value = 5
        srv.container_id.return_value = 5
        sess = Session(srv, ("127.0.0.1", 19132), 1400, 100)
        sess.open_crafting_table((10, 64, 10))
        self.assertTrue(sess.open_window)
        self.assertEqual(sess.open_window_id, 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_block_containers.py -v`
Expected: FAIL with `AttributeError: 'Session' object has no attribute 'open_crafting_table'`

- [ ] **Step 3: Implement block container opening and storage**
  - In `pywer/server/server.py`:
    - Add `self.chests = {}` in `Server.__init__`.
    - In `Server.break_block`: if broken block is `"chest"` and `(x, y, z)` in `self.chests`, drop all stored items and pop entry.
  - In `pywer/player/session.py`:
    - Add `open_crafting_table(self, pos)`: opens window type 1 (`WINDOW_WORKBENCH`) at `pos`.
    - Add `open_chest(self, pos)`: opens window type 0 (`WINDOW_CONTAINER`) at `pos`, binds 27 slots to `self.window_to_container`.
    - In `try_place_block(tx)`: if `not self.sneaking` and clicked block is `"crafting_table"` or `"chest"`, open container and return `True`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_block_containers.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 4**

```bash
git add pywer/server/server.py pywer/player/session.py tests/test_block_containers.py
git commit -m "feat: implement interactive crafting table and chest block containers"
```

---

### Task 5: End-to-End Verification & Regression Testing

**Files:**
- Test: All tests in `tests/`
- Tool: `tools/smoke_test_inventory.py`

- [ ] **Step 1: Run complete test suite across all modules**

Run: `python -m unittest discover -s tests -v`
Expected: ALL tests PASS (existing 12 tests + new recipe, mapping, action, and container tests).

- [ ] **Step 2: Write and run inventory smoke test**

Run a script that performs a complete crafting sequence (log $\to$ planks $\to$ crafting table) and creative item take.
Expected: PASS with 0 errors.

- [ ] **Step 3: Commit Task 5**

```bash
git add tools/smoke_test_inventory.py
git commit -m "test: add end-to-end inventory and container smoke test"
```
