# Entity Architecture & Physics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a generic entity architecture with spatial chunk-bucketed ticking, projectiles (arrows, snowballs), refactored dropped items, basic mobs (cows, zombies) with simple AI, collision raycasting, Bedrock `AddActorPacket` encoding, and player bow/snowball firing.

**Architecture:** An object-oriented entity hierarchy rooted at `Entity` (`pywer.entity.base`) branches into `ItemEntity`, `Projectile` (`Arrow`, `Snowball`), and `LivingEntity` (`Mob`, `Cow`, `Zombie`). An `EntityManager` (`pywer.entity.manager`) maintains spatial chunk indexing `(cx, cz) -> set[Entity]` and culls ticking to active player simulation distance ($R \le 4$ chunks). A discrete vector raycasting engine in `pywer.entity.physics` detects block and entity collisions with knockback and damage dispatch. Player interactions in `Session` handle bow releases and snowball throws.

**Tech Stack:** Python 3.10+, Minecraft Bedrock Protocol 766 (v1.21.50), standard library `unittest`.

**Spec:** [`docs/superpowers/specs/2026-10-03-entity-architecture-and-physics-design.md`](file:///c:/Users/Mani/Desktop/Pywer/docs/superpowers/specs/2026-10-03-entity-architecture-and-physics-design.md)

## Global Constraints
- Target Bedrock protocol: 766 (v1.21.50).
- Pure standard library Python only (no external pip dependencies).
- Game simulation state (positions, inventories, entity registries) remains strictly single-threaded on the main loop.
- No statement semicolons or un-expanded compound lines. All code must conform to PEP 8.
- 100% preservation of existing comments, network bitmasks, and endianness.

---

### Task 1: Core Entity Hierarchy & ItemEntity Refactor (`pywer.entity.base`, `pywer.entity.item`)

**Files:**
- Create: `pywer/entity/__init__.py`
- Create: `pywer/entity/base.py`
- Create: `pywer/entity/item.py`
- Test: `tests/test_entity_hierarchy.py`

**Interfaces:**
- Produces:
  - `Entity(srv, rid, pos, motion, pitch, yaw)`: Base class with `.chunk`, `.aabb()`, `.tick(now, dt, world_is_solid)`
  - `ItemEntity(srv, rid, item_key, count, pos, motion)`: Subclass with gravity, drag, ground friction, merging, pickup check

- [ ] **Step 1: Write failing unit tests for `Entity` base and `ItemEntity`**

```python
# tests/test_entity_hierarchy.py
import unittest
from unittest.mock import MagicMock
from pywer.entity.base import Entity
from pywer.entity.item import ItemEntity

class TestEntityHierarchy(unittest.TestCase):
    def test_entity_base_properties(self):
        srv = MagicMock()
        e = Entity(srv, 1001, pos=(18.5, 64.0, 32.5), motion=(0.1, 0.2, 0.3), pitch=10.0, yaw=45.0)
        self.assertEqual(e.rid, 1001)
        self.assertEqual(e.pos, (18.5, 64.0, 32.5))
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
        item = ItemEntity(srv, 1002, "stone", 16, pos=(0.0, 65.0, 0.0), motion=(0.0, 0.0, 0.0))
        self.assertEqual(item.item_key, "stone")
        self.assertEqual(item.count, 16)
        # Mock world_is_solid: solid only at y <= 63
        world_is_solid = lambda x, y, z: y <= 63
        moved = item.tick(0.0, 0.05, world_is_solid)
        self.assertTrue(moved)
        self.assertLess(item.pos[1], 65.0)  # Gravity pulled it down
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_entity_hierarchy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.entity'`

- [ ] **Step 3: Implement `pywer/entity/__init__.py`, `pywer/entity/base.py`, and `pywer/entity/item.py`**

```python
# pywer/entity/base.py
"""Base class for all non-player world actors."""

class Entity:
    """Base class for all non-player world actors."""

    def __init__(self, srv, rid, pos=(0.0, 0.0, 0.0), motion=(0.0, 0.0, 0.0), pitch=0.0, yaw=0.0):
        self.srv = srv
        self.rid = rid
        self.pos = tuple(float(v) for v in pos)
        self.motion = tuple(float(v) for v in motion)
        self.pitch = float(pitch)
        self.yaw = float(yaw)
        self.head_yaw = float(yaw)
        self.on_ground = False
        self.dead = False
        self.age = 0.0
        self.width = 0.25
        self.height = 0.25
        self.identifier = "minecraft:actor"
        self.metadata = {}

    @property
    def chunk(self):
        return (int(self.pos[0]) >> 4, int(self.pos[2]) >> 4)

    def aabb(self):
        """Bounding box: (min_x, min_y, min_z, max_x, max_y, max_z)."""
        hw = self.width / 2.0
        return (
            self.pos[0] - hw, self.pos[1], self.pos[2] - hw,
            self.pos[0] + hw, self.pos[1] + self.height, self.pos[2] + hw,
        )

    def tick(self, now, dt, world_is_solid):
        """Advance entity state by dt seconds. Returns True if position changed."""
        raise NotImplementedError
```

```python
# pywer/entity/item.py
"""Dropped item entities with gravity, drag, ground friction, and pickup rules."""

import math
from .base import Entity

GRAVITY = 0.08
HORIZONTAL_DRAG = 0.7
GROUND_FRICTION = 0.5
PICKUP_DELAY = 0.5
LIFETIME = 300.0
PICKUP_RANGE = 1.5
MERGE_RANGE = 0.75

class ItemEntity(Entity):
    """Dropped item stack in world."""

    def __init__(self, srv, rid, item_key, count=1, pos=(0.0, 0.0, 0.0), motion=(0.0, 0.0, 0.0), spawned_at=0.0):
        super().__init__(srv, rid, pos, motion)
        self.item_key = item_key
        self.count = count
        self.spawned_at = spawned_at
        self.pickup_at = spawned_at + PICKUP_DELAY
        self.identifier = "minecraft:item"
        self.width = 0.25
        self.height = 0.25

    def tick(self, now, dt, world_is_solid):
        self.age = now - self.spawned_at
        if self.age >= LIFETIME:
            self.dead = True
            return False

        x, y, z = self.pos
        vx, vy, vz = self.motion

        def solid_at(px, py, pz):
            return world_is_solid(math.floor(px), math.floor(py), math.floor(pz))

        vy -= GRAVITY
        nx, ny, nz = x + vx, y + vy, z + vz

        if solid_at(nx, y, z):
            vx = 0.0
            nx = x
        if solid_at(x, y, nz):
            vz = 0.0
            nz = z
        if solid_at(nx, ny, nz) or solid_at(nx, y - 0.02, nz):
            vy = 0.0
            ny = y

        resting = solid_at(nx, ny - 0.2, nz)
        if resting:
            vy = 0.0
            vx *= GROUND_FRICTION
            vz *= GROUND_FRICTION
            if abs(vx) < 0.01:
                vx = 0.0
            if abs(vz) < 0.01:
                vz = 0.0
        else:
            vx *= HORIZONTAL_DRAG
            vz *= HORIZONTAL_DRAG

        moved = (nx, ny, nz) != (x, y, z)
        self.pos = (nx, ny, nz)
        self.motion = (vx, vy, vz)
        self.on_ground = resting
        return moved

    def can_pickup(self, player_feet, now):
        if now < self.pickup_at or self.dead:
            return False
        px, py, pz = player_feet
        dx, dy, dz = self.pos[0] - px, self.pos[1] - py, self.pos[2] - pz
        return (dx * dx + dy * dy + dz * dz) <= (PICKUP_RANGE * PICKUP_RANGE)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_entity_hierarchy.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 1**

```bash
git add pywer/entity/ tests/test_entity_hierarchy.py
git commit -m "feat: implement generic Entity base and ItemEntity classes"
```

---

### Task 2: Projectile & Living Mob Hierarchy (`pywer.entity.projectile`, `pywer.entity.mob`)

**Files:**
- Create: `pywer/entity/projectile.py`
- Create: `pywer/entity/mob.py`
- Test: `tests/test_projectiles_and_mobs.py`

**Interfaces:**
- Produces:
  - `Projectile`: `Arrow` (damage, in_ground flag), `Snowball` (knockback, shatter)
  - `LivingEntity`: Health tracking, damage taking, knockback calculation, death state
  - `Mob`: `Cow` (wander AI), `Zombie` (target player AI within 16 blocks, attack on contact)

- [ ] **Step 1: Write failing unit tests for projectiles and mobs**

```python
# tests/test_projectiles_and_mobs.py
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
        arrow.stick_in_ground()
        self.assertTrue(arrow.in_ground)
        self.assertEqual(arrow.motion, (0.0, 0.0, 0.0))

    def test_mob_health_and_damage(self):
        srv = MagicMock()
        zombie = Zombie(srv, 3001, pos=(10, 64, 10))
        self.assertEqual(zombie.identifier, "minecraft:zombie")
        self.assertEqual(zombie.health, 20.0)
        self.assertFalse(zombie.dead)
        zombie.damage(5.0, source_rid=50)
        self.assertEqual(zombie.health, 15.0)
        zombie.damage(20.0, source_rid=50)
        self.assertEqual(zombie.health, 0.0)
        self.assertTrue(zombie.dead)

    def test_passive_mob_cow(self):
        srv = MagicMock()
        cow = Cow(srv, 3002, pos=(5, 64, 5))
        self.assertEqual(cow.identifier, "minecraft:cow")
        self.assertEqual(cow.health, 10.0)
        self.assertEqual(cow.ai_state, "WANDER")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_projectiles_and_mobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.entity.projectile'`

- [ ] **Step 3: Implement `pywer/entity/projectile.py` and `pywer/entity/mob.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_projectiles_and_mobs.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 2**

```bash
git add pywer/entity/projectile.py pywer/entity/mob.py tests/test_projectiles_and_mobs.py
git commit -m "feat: implement projectile and living mob entity classes"
```

---

### Task 3: Raycasting & Collision Physics Engine (`pywer.entity.physics`)

**Files:**
- Create: `pywer/entity/physics.py`
- Test: `tests/test_entity_physics.py`

**Interfaces:**
- Produces:
  - `raycast_step(start_pos, motion, world_is_solid, step_size=0.25)`: Returns `(hit_type, hit_pos, block_pos, face)`
  - `aabb_intersects_ray(aabb, start_pos, motion)`: Line-box intersection test
  - `check_projectile_collisions(projectile, nearby_entities, world_is_solid)`: Returns `(hit_type, target_or_block, hit_pos)`

- [ ] **Step 1: Write failing unit tests for discrete raycasting and line-AABB collision**

```python
# tests/test_entity_physics.py
import unittest
from pywer.entity.physics import raycast_step, aabb_intersects_ray

class TestEntityPhysics(unittest.TestCase):
    def test_raycast_hits_block(self):
        # Ray from (0.5, 64.5, 0.5) with motion (2.0, 0.0, 0.0) towards solid block at x=2
        world_is_solid = lambda x, y, z: x >= 2
        hit_type, hit_pos, block_pos, face = raycast_step((0.5, 64.5, 0.5), (2.0, 0.0, 0.0), world_is_solid)
        self.assertEqual(hit_type, "block")
        self.assertEqual(block_pos[0], 2)

    def test_aabb_intersects_ray(self):
        # Target AABB at [5, 64, 5] to [6, 66, 6]
        target_aabb = (5.0, 64.0, 5.0, 6.0, 66.0, 6.0)
        # Ray starting at (0, 65, 5.5) moving +x towards (10, 65, 5.5)
        hit = aabb_intersects_ray(target_aabb, (0.0, 65.0, 5.5), (10.0, 0.0, 0.0))
        self.assertTrue(hit)
        # Ray aimed away
        miss = aabb_intersects_ray(target_aabb, (0.0, 65.0, 5.5), (0.0, 10.0, 0.0))
        self.assertFalse(miss)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_entity_physics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.entity.physics'`

- [ ] **Step 3: Implement `pywer/entity/physics.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_entity_physics.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 3**

```bash
git add pywer/entity/physics.py tests/test_entity_physics.py
git commit -m "feat: implement discrete raycast and entity collision physics"
```

---

### Task 4: Spatial Chunk-Bucketed EntityManager & Server Integration (`pywer.entity.manager`, `pywer.server.server`)

**Files:**
- Create: `pywer/entity/manager.py`
- Modify: `pywer/server/server.py`
- Test: `tests/test_entity_manager.py`

**Interfaces:**
- Produces:
  - `EntityManager(srv)`:
    - `alloc_rid() -> int`
    - `spawn(entity_cls, *args, **kwargs) -> Entity`
    - `remove(rid) -> None`
    - `tick(now, dt, world_is_solid) -> None`
    - `entities_in_chunk(cx, cz) -> set[Entity]`
    - `entities_near(pos, radius) -> list[Entity]`
- Integrates:
  - `Server.entity_mgr`: Replaces procedural `self.item_entities` with `EntityManager`
  - In `Server.tick`: executes `self.entity_mgr.tick(now, dt, is_solid)`

- [ ] **Step 1: Write failing unit tests for `EntityManager` spatial tracking and simulation distance**

```python
# tests/test_entity_manager.py
import unittest
from unittest.mock import MagicMock
from pywer.entity.manager import EntityManager
from pywer.entity.item import ItemEntity

class TestEntityManager(unittest.TestCase):
    def test_spatial_bucketing(self):
        srv = MagicMock()
        srv.playing.return_value = []
        mgr = EntityManager(srv)
        item = mgr.spawn(ItemEntity, "stone", 1, pos=(18.0, 64.0, 34.0))
        # Chunk (1, 2)
        self.assertIn((1, 2), mgr.chunk_index)
        self.assertIn(item, mgr.chunk_index[(1, 2)])

        # Move to Chunk (2, 2)
        mgr.update_entity_pos(item, (33.0, 64.0, 34.0))
        self.assertNotIn(item, mgr.chunk_index.get((1, 2), set()))
        self.assertIn(item, mgr.chunk_index[(2, 2)])

    def test_simulation_distance_culling(self):
        srv = MagicMock()
        p = MagicMock()
        p.cx, p.cz = 0, 0
        srv.playing.return_value = [p]
        mgr = EntityManager(srv)

        # Entity in active chunk (0, 0)
        near_item = mgr.spawn(ItemEntity, "dirt", 1, pos=(5.0, 65.0, 5.0))
        # Entity far away in chunk (20, 20)
        far_item = mgr.spawn(ItemEntity, "sand", 1, pos=(320.0, 65.0, 320.0))

        world_is_solid = lambda x, y, z: y <= 63
        mgr.tick(0.0, 0.05, world_is_solid)

        # Near item ticked and moved down
        self.assertLess(near_item.pos[1], 65.0)
        # Far item culled from ticking
        self.assertEqual(far_item.pos[1], 65.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_entity_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.entity.manager'`

- [ ] **Step 3: Implement `pywer/entity/manager.py` and modify `pywer/server/server.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_entity_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 4**

```bash
git add pywer/entity/manager.py pywer/server/server.py tests/test_entity_manager.py
git commit -m "feat: implement spatial chunk-bucketed entity manager and server integration"
```

---

### Task 5: Bedrock Actor Packet Encoders & Player Firing Pipeline (`pywer.packets.entity`, `pywer.player.session`)

**Files:**
- Modify: `pywer/packets/entity.py`
- Modify: `pywer/player/session.py`
- Test: `tests/test_player_projectiles.py`

**Interfaces:**
- Produces:
  - `build_add_actor(entity)`: Encodes `PID_ADD_ACTOR = 13` packet
  - `build_remove_actor(rid)`: Encodes `PID_REMOVE_ACTOR = 14` packet
  - Bow release handling: Spawns `Arrow` with charged look velocity, consumes arrow
  - Snowball right-click handling: Spawns `Snowball`, consumes snowball

- [ ] **Step 1: Write failing unit tests for bow shooting and snowball throwing**

```python
# tests/test_player_projectiles.py
import unittest
from unittest.mock import MagicMock
from pywer.player.session import Session
from pywer.packets.entity import build_add_actor
from pywer.entity.projectile import Arrow, Snowball

class TestPlayerProjectiles(unittest.TestCase):
    def test_build_add_actor_wire_format(self):
        arrow = Arrow(MagicMock(), 9001, 100, pos=(1.0, 64.0, 1.0), motion=(0.5, 0.0, 0.5))
        payload = build_add_actor(arrow)
        self.assertIsInstance(payload, bytes)
        self.assertGreater(len(payload), 10)
        self.assertIn(b"minecraft:arrow", payload)

    def test_bow_release_spawns_arrow_and_consumes_inventory(self):
        srv = MagicMock()
        srv.next_rid = 1
        srv.key = (MagicMock(), MagicMock())
        srv.entity_mgr = MagicMock()
        sess = Session(srv, ("127.0.0.1", 19132), 1400, 100)
        sess._set_feet((0, 64, 0))
        sess.inventory[0] = (261, 1, 0)  # Bow in slot 0
        sess.inventory[9] = (262, 5, 0)  # 5 Arrows in slot 9
        sess.selected_slot = 0
        sess.gamemode_is_creative = lambda: False

        # Release bow transaction
        tx = {"action": 0, "hotbar": 0, "item": {"id": 261}}
        sess.handle_release_item(tx)

        # Arrow spawned via entity_mgr
        srv.entity_mgr.spawn.assert_called()
        # 1 arrow consumed from inventory
        self.assertEqual(sess.inventory[9], (262, 4, 0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_player_projectiles.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_add_actor'` or `AttributeError`

- [ ] **Step 3: Implement `build_add_actor` in `pywer/packets/entity.py` and bow/snowball handling in `pywer/player/session.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_player_projectiles.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 5**

```bash
git add pywer/packets/entity.py pywer/player/session.py tests/test_player_projectiles.py
git commit -m "feat: implement AddActorPacket and player projectile firing"
```

---

### Task 6: End-to-End Verification & Entity Smoke Test (`tools/smoke_test_entities.py`)

**Files:**
- Create: `tools/smoke_test_entities.py`
- Run: Full test suite

- [ ] **Step 1: Write and run end-to-end smoke test**

Automated verification covering:
1. Spawning `Zombie`, `Cow`, `Arrow`, `Snowball`, and `ItemEntity` into `EntityManager`.
2. Simulating projectile flight with `raycast_step`.
3. Verifying projectile hit on `Zombie`, applying damage & knockback.
4. Verifying hostile `Zombie` AI targeting survival player within 16 blocks.
5. Verifying `ItemEntity` player pickup and inventory merging.
6. Despawning dead actors and verifying `PID_REMOVE_ACTOR` packet emission.

- [ ] **Step 2: Run complete project test suite**

Run: `python -m unittest discover -s tests -v`
Expected: ALL unit tests PASS.

- [ ] **Step 3: Commit Task 6**

```bash
git add tools/smoke_test_entities.py
git commit -m "test: add end-to-end entity architecture and physics smoke test"
```
