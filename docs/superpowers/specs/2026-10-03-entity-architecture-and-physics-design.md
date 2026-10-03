# Milestone 3: Entity Architecture & Physics Design Specification

**Target Protocol:** Minecraft Bedrock Edition Protocol 766 (v1.21.50)  
**Implementation Language:** Pure Python 3.10+ (Standard Library only)  
**Date:** 2026-10-03  

---

## 1. Problem Statement & Context

In the current Pywer codebase:
- Dropped items exist as ad-hoc dictionaries in `Server.item_entities` with procedural physics in `pywer/world/item_entity.py`.
- No generic entity class hierarchy or abstraction exists for non-player world entities.
- Projectiles (arrows, snowballs) do not exist, preventing ranged combat and throwables.
- Non-player living entities (passive animals, hostile mobs) do not exist, and there is no framework for ticking non-player AI.
- `AddActorPacket` (PID 13 / 0x0d) is not implemented on the server, only `AddPlayerPacket` (PID 12) and `AddItemActorPacket` (PID 15).
- All dropped items tick globally in a single flat list, with no spatial culling based on player simulation distance.

Milestone 3 establishes a clean, modular entity subsystem that provides a generic `Entity` base, specialized subclasses (`ItemEntity`, `Projectile`, `LivingEntity` / `Mob`), a spatial chunk-bucketed `EntityManager`, discrete physics raycasting, Bedrock packet encoding, and full player interaction for bow shooting and snowball throwing.

---

## 2. Goals & Non-Goals

### Goals
1. **Generic Entity Base Hierarchy (`pywer.entity.base`):**
   - Common entity state: runtime ID (`rid`), position `(x, y, z)`, motion `(vx, vy, vz)`, orientation `(pitch, yaw, head_yaw)`, `on_ground`, `dead`, `age`, bounding box dimensions `(width, height)`, and Bedrock metadata flags.
2. **ItemEntity Refactor (`pywer.entity.item`):**
   - Cleanly inherit from `Entity`. Retain gravitational drag, ground friction, stack merging within 0.75 blocks, pickup delay (0.5s), 5-minute lifetime, and proximity pickup checks.
3. **Projectile System (`pywer.entity.projectile`):**
   - Generic `Projectile` class with shooter attribution, drag, gravity, and lifetime tracking.
   - `Arrow`: Sticks into solid blocks on impact, deals damage and applies knockback to living entities and players.
   - `Snowball`: Breaks on impact with solid blocks or entities, deals knockback without direct damage, emits particle/sound events.
4. **Living Entities & Mobs (`pywer.entity.mob`):**
   - `LivingEntity` base with `health`, `max_health`, knockback resistance, hurt cooldown, and death animation/drops.
   - `Cow`: Passive mob with idle/wander state machine.
   - `Zombie`: Hostile mob with player detection (within 16 blocks), stepping toward target, and contact melee damage + knockback.
5. **Spatial Chunk-Bucketed Ticking (`pywer.entity.manager`):**
   - Entities indexed in `dict[tuple[int, int], set[Entity]]` by chunk coordinate `(cx, cz)`.
   - Dynamic simulation distance: only entities in active chunks around connected players ($R \le 4$ chunks) tick each cycle.
6. **Network Protocol Support:**
   - Implement `build_add_actor` for `PID_ADD_ACTOR = 13`.
   - Maintain `PID_REMOVE_ACTOR = 14`, `PID_MOVE_ACTOR_ABSOLUTE = 18`, and `PID_SET_ACTOR_MOTION = 40`.
7. **Player Firing Integration:**
   - Bow release (`ReleaseItemTransactionData`) shoots arrows with charged velocity and consumes arrows in survival.
   - Snowball right-click (`UseItemTransactionData`) launches snowballs and consumes items in survival.

### Non-Goals
- Full pathfinding with complex A* graph search (deferred; simple vector stepping with solid block step-up is sufficient for basic mob movement).
- Entity persistence to disk (entities will spawn dynamically in-world or via commands; disk serialization belongs to world storage expansion).
- Complex breeding, trading, or equipment inventories on mobs.

---

## 3. Architecture & Class Hierarchy

```
                  ┌──────────────────────┐
                  │        Entity        │
                  │ (pywer.entity.base)  │
                  └──────────┬───────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
┌────────┴────────┐ ┌────────┴────────┐ ┌────────┴────────┐
│   ItemEntity    │ │   Projectile    │ │  LivingEntity   │
│(pywer.entity.   │ │ (pywer.entity.  │ │ (pywer.entity.  │
│      item)      │ │   projectile)   │ │      mob)       │
└─────────────────┘ └────────┬────────┘ └────────┬────────┘
                             │                   │
                      ┌──────┴──────┐     ┌──────┴──────┐
                      │             │     │             │
                  ┌───┴───┐     ┌───┴───┐ ┌───┴───┐ ┌───┴───┐
                  │ Arrow │     │Snowball││  Cow  │ │Zombie │
                  └───────┘     └───────┘ └───────┘ └───────┘
```

### 3.1 Entity Base (`pywer/entity/base.py`)
```python
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
        """Bounding box: [min_x, min_y, min_z, max_x, max_y, max_z]."""
        hw = self.width / 2.0
        return (self.pos[0] - hw, self.pos[1], self.pos[2] - hw,
                self.pos[0] + hw, self.pos[1] + self.height, self.pos[2] + hw)

    def tick(self, now, dt, world_is_solid):
        """Advance entity simulation state by dt seconds. Returns True if position changed."""
        raise NotImplementedError
```

### 3.2 Projectiles (`pywer/entity/projectile.py`)
- **`Projectile(Entity)`**:
  - `shooter_rid`: RID of the actor who fired the projectile (ignored in collisions for 5 ticks).
  - `damage`: Base damage value dealt on entity collision.
  - `gravity`: Vertical acceleration per tick (e.g. 0.05 for arrows, 0.03 for snowballs).
  - `drag`: Air drag applied per tick (0.01).
- **`Arrow(Projectile)`**:
  - `in_ground`: Boolean indicating if arrow has stuck into a solid block.
  - When in ground: motion becomes `(0, 0, 0)`, gravity suspended, despawns after 60 seconds.
  - On entity hit: deals damage, applies horizontal knockback, attaches hurt sound/animation, and despawns.
- **`Snowball(Projectile)`**:
  - On block or entity hit: deals 0 damage, applies mild knockback to entities, emits `PID_LEVEL_EVENT` particle, and despawns immediately.

### 3.3 Living Entities & Mobs (`pywer/entity/mob.py`)
- **`LivingEntity(Entity)`**:
  - `health`: Current hit points.
  - `max_health`: Maximum hit points.
  - `hurt_time`: Cooldown ticks remaining before entity can take damage again (invulnerability frames).
  - `damage(amount, source=None)`: Decrements health, applies knockback, plays hurt animation/sound, triggers death if health $\le 0$.
- **`Mob(LivingEntity)`**:
  - `ai_state`: Enum (`IDLE`, `WANDER`, `TARGET`).
  - `target_player`: Reference to targeted `Session` (if hostile or provoked).
  - `speed`: Movement stepping speed.
- **`Zombie(Mob)`**:
  - `identifier = "minecraft:zombie"`, `width = 0.6`, `height = 1.9`, `max_health = 20.0`, `damage_amount = 3.0`.
  - Scans for nearest survival player within 16 blocks; steps towards player; attacks if within 1.5 blocks.
- **`Cow(Mob)`**:
  - `identifier = "minecraft:cow"`, `width = 0.9`, `height = 1.4`, `max_health = 10.0`.
  - Wanders randomly within 8 blocks of spawn origin; flees briefly if damaged.

---

## 4. Spatial Chunk-Bucketed Simulation (`pywer/entity/manager.py`)

### 4.1 Chunk Index Maintenance
Entities register with `EntityManager`:
- Entities are placed into bucket `self.chunk_index[(cx, cz)]`.
- Upon moving between chunks, the entity is safely transferred from the previous chunk set to the new one.
- When an entity dies or is removed, it is purged from both the global dictionary and the spatial bucket.

### 4.2 Active Simulation Radius
Each tick:
1. Active chunks are collected from all online players:
   $$\text{ActiveChunks} = \bigcup_{p \in \text{sessions}} \{ (\lfloor p.x/16 \rfloor + dx, \lfloor p.z/16 \rfloor + dz) \mid -4 \le dx, dz \le 4 \}$$
2. Entities in active chunks execute `tick(now, dt, world_is_solid)`.
3. If an entity moved, broadcast `build_move_actor_absolute` or `build_set_actor_motion` to players within render distance.
4. Entities in chunks outside `ActiveChunks` remain stationary and do not consume CPU cycles.

---

## 5. Physics & Collision Detection (`pywer/entity/physics.py`)

### 5.1 Discrete Raycast Stepping
To prevent high-velocity projectiles from tunneling through voxels:
```python
def raycast_step(start_pos, motion, world_is_solid, step_size=0.25):
    """
    Sub-steps along motion vector.
    Returns: (hit_type, hit_pos, block_pos, face)
      - hit_type: 'block' or 'none'
    """
```
- Total displacement $D = \|\vec{v}\|$.
- Number of sub-steps $N = \max(1, \lceil D / \text{step\_size} \rceil)$.
- At each sub-step $t \in [1..N]$, check if $\lfloor \vec{p}_0 + \vec{v} \cdot (t / N) \rfloor$ is solid.
- First solid voxel encountered terminates the raycast and reports the hit point.

### 5.2 AABB Entity Intersections
For each sub-step, test line-box intersection against all living actors (mobs and players) within the entity's chunk and adjacent chunks:
- Discard the shooter for the first 5 ticks to avoid self-collision upon release.
- First intersecting entity triggers `projectile.on_hit_entity(target)`.

---

## 6. Network Protocol & Packet Encoders

### 6.1 `AddActorPacket` (`PID_ADD_ACTOR = 13`)
Wire schema for Bedrock Protocol 766:
1. `entity_unique_id`: zigzag varlong (`self.rid`).
2. `entity_runtime_id`: varuint64 (`self.rid`).
3. `identifier`: string (e.g. `"minecraft:arrow"`).
4. `pos`: Vec3 float `(x, y, z)`.
5. `motion`: Vec3 float `(vx, vy, vz)`.
6. `pitch`, `yaw`, `head_yaw`: float32.
7. `attributes`: varuint32 count + attribute structures (movement, health).
8. `metadata`: Bedrock actor metadata dictionary (flags, scale, bounding box).
9. `synced_properties`: 0 ints, 0 floats.
10. `links`: 0 varuint32.

### 6.2 Movement & Removal
- `PID_MOVE_ACTOR_ABSOLUTE` (18): Emits runtime ID, flags, Vec3 position, pitch byte, yaw byte, head_yaw byte.
- `PID_REMOVE_ACTOR` (14): Emits zigzag varlong runtime ID to despawn the entity on client screens.
- `PID_SET_ACTOR_MOTION` (40): Emits runtime ID, Vec3 motion, tick counter.

---

## 7. Player Firing Integration

### 7.1 Bow Release
In `pywer/player/session.py` when handling `ReleaseItemTransactionData` (`PID_INVENTORY_TRANSACTION`):
- Action `ACTION_RELEASE`:
  - Check held item: if `item_id` is Bow (`ID_BOW = 261`):
    - Compute charge speed: $\text{speed} = \min(3.0, \max(0.5, \text{pull\_duration} \cdot 3.0))$.
    - In survival mode, scan inventory for arrow (`ID_ARROW = 262`); consume 1 arrow. If no arrow exists, abort firing.
    - Direction vector calculated from pitch/yaw:
      $$v_x = -\sin(\text{yaw}) \cdot \cos(\text{pitch}) \cdot \text{speed}$$
      $$v_y = -\sin(\text{pitch}) \cdot \text{speed}$$
      $$v_z = \cos(\text{yaw}) \cdot \cos(\text{pitch}) \cdot \text{speed}$$
    - Spawn `Arrow` at `(x, y + 1.62, z)` with initial motion $\vec{v}$.
    - Play bow shoot sound.

### 7.2 Snowball Throwing
In `pywer/player/session.py` when handling `UseItemTransactionData`:
- Action `ACTION_CLICK_AIR` or `ACTION_CLICK_BLOCK`:
  - If held item is Snowball (`ID_SNOWBALL = 332`):
    - In survival mode, consume 1 snowball from held slot.
    - Spawn `Snowball` at `(x, y + 1.62, z)` with velocity directed along look vector with speed $1.5$.
    - Play throw sound.

---

## 8. Verification & Testing Strategy

1. **Unit Tests:**
   - `tests/test_entity_hierarchy.py`: Class hierarchy, bounding boxes, attributes, and metadata.
   - `tests/test_entity_physics.py`: Discrete raycasting against voxels and entity hitboxes.
   - `tests/test_entity_manager.py`: Spatial chunk-bucketing, simulation distance culling, RID allocation.
   - `tests/test_entity_packets.py`: Wire serialization of `PID_ADD_ACTOR` (13), `PID_REMOVE_ACTOR` (14).
   - `tests/test_player_projectiles.py`: Bow release and snowball throwing inventory consumption and projectile spawning.
2. **End-to-End Smoke Test (`tools/smoke_test_entities.py`):**
   - Full automated simulation verifying spawn, spatial indexing, bow firing, collision damage, zombie targeting, and despawn.
