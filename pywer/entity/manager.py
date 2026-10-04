"""Spatial chunk-bucketed entity manager.

Handles entity lifecycle, spatial indexing by (chunk_x, chunk_z),
simulation distance culling, movement synchronization, and item pickups.
"""

import math
import random
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

from ..event import EntityDespawnEvent, EntitySpawnEvent
from ..event import manager as events
from .base import Entity
from .item import ItemEntity, MERGE_RANGE, PICKUP_DELAY


def resolve_actor(srv: Any, rid: Any) -> Any:
    """Resolve a network actor id to a player session or a world entity.

    Players live in `srv.playing()`, mobs/items/projectiles live in
    `srv.entity_mgr.entities`. Searching only one of the two collections makes every
    RID lookup wrong for the other half of the world: a punch at a zombie found no
    target and was silently dropped, and an arrow shot by a skeleton could not be
    attributed to its shooter, so it produced no damager, no knockback and a death
    message that read "died" instead of "slain by skeleton".

    Players are checked first so an id collision (there is none by construction, but
    a player is the more specific answer) never shadows a session.
    """
    if rid is None:
        return None
    playing = getattr(srv, "playing", None)
    if callable(playing):
        for actor in playing():
            if getattr(actor, "rid", None) == rid:
                return actor
    entities = getattr(getattr(srv, "entity_mgr", None), "entities", None)
    if isinstance(entities, dict):
        return entities.get(rid)
    return None


class EntityManager:
    """Manages all world entities with spatial chunk indexing and distance culling."""

    def __init__(self, srv: Any) -> None:
        self.srv = srv
        self.entities: Dict[int, Entity] = {}
        self.chunk_index: Dict[Tuple[int, int], Set[Entity]] = {}
        self._local_rid = 1000

    def alloc_rid(self) -> int:
        """Allocates unique actor runtime ID."""
        if hasattr(self.srv, "next_rid"):
            rid = self.srv.next_rid
            self.srv.next_rid += 1
            return rid
        self._local_rid += 1
        return self._local_rid

    def spawn(self, entity_cls: Type[Entity], *args: Any, **kwargs: Any) -> Optional[Entity]:
        """Spawns an entity, adds it to the spatial index, and broadcasts spawn packet.

        Returns None when a plugin cancelled the EntitySpawnEvent. Callers that ignore
        the return value therefore spawn nothing rather than a half-registered entity:
        the rid is allocated first, and an allocated-but-unused id is harmless.
        """
        rid = kwargs.pop("rid", None)
        if rid is None:
            rid = self.alloc_rid()

        entity = entity_cls(self.srv, rid, *args, **kwargs)
        ev = events.call(EntitySpawnEvent(entity, entity.pos))
        if ev.is_cancelled:
            return None
        self.entities[rid] = entity
        chunk = entity.chunk
        if chunk not in self.chunk_index:
            self.chunk_index[chunk] = set()
        self.chunk_index[chunk].add(entity)

        self._broadcast_spawn(entity)
        return entity

    def _broadcast_spawn(self, entity: Entity) -> None:
        """Broadcasts AddActorPacket or AddItemActorPacket to connected players."""
        if not (hasattr(self.srv, "broadcast") and hasattr(self.srv, "playing") and self.srv.playing()):
            return

        try:
            from ..protocol.packet_ids import PID_ADD_ACTOR, PID_ADD_ITEM_ACTOR
            from ..player.session import Session

            if isinstance(entity, ItemEntity):
                from ..packets.item_actor import build_add_item_actor

                pkt = Session._pk(
                    PID_ADD_ITEM_ACTOR,
                    build_add_item_actor(
                        entity.rid,
                        entity.item_key,
                        entity.count,
                        entity.pos,
                        entity.motion,
                    ),
                )
                self.srv.broadcast([pkt])
            else:
                try:
                    from ..packets.entity import build_add_actor

                    pkt = Session._pk(PID_ADD_ACTOR, build_add_actor(entity))
                    self.srv.broadcast([pkt])
                except (ImportError, AttributeError):
                    pass
        except Exception:
            pass

    def remove(self, rid: int) -> Optional[Entity]:
        """Despawns an entity, purges it from chunk buckets, and broadcasts remove packet."""
        entity = self.entities.pop(rid, None)
        if entity is not None:
            entity.dead = True
            chunk = entity.chunk
            if chunk in self.chunk_index:
                self.chunk_index[chunk].discard(entity)
                if not self.chunk_index[chunk]:
                    del self.chunk_index[chunk]

            # Fired once the entity is out of every index, so a handler that queries the
            # manager sees the same state the rest of the server already sees.
            events.call(EntityDespawnEvent(entity))

            if hasattr(self.srv, "broadcast"):
                try:
                    from ..protocol.packet_ids import PID_REMOVE_ACTOR
                    from ..player.session import Session
                    from ..util.serializer import ByteWriter

                    pkt = Session._pk(
                        PID_REMOVE_ACTOR, ByteWriter().write_varint64(rid).get()
                    )
                    self.srv.broadcast([pkt])
                except Exception:
                    pass

        return entity

    def update_entity_pos(
        self, entity: Entity, new_pos: Tuple[float, float, float]
    ) -> None:
        """Updates entity position and migrates spatial chunk bucket if crossed."""
        old_chunk = entity.chunk
        entity.pos = (float(new_pos[0]), float(new_pos[1]), float(new_pos[2]))
        new_chunk = entity.chunk

        if old_chunk != new_chunk:
            if old_chunk in self.chunk_index:
                self.chunk_index[old_chunk].discard(entity)
                if not self.chunk_index[old_chunk]:
                    del self.chunk_index[old_chunk]
            if new_chunk not in self.chunk_index:
                self.chunk_index[new_chunk] = set()
            self.chunk_index[new_chunk].add(entity)

    def entities_in_chunk(self, cx: int, cz: int) -> Set[Entity]:
        """Returns all entities in a given chunk coordinate."""
        return set(self.chunk_index.get((cx, cz), set()))

    def entities_near(
        self, pos: Tuple[float, float, float], radius: float
    ) -> List[Entity]:
        """Finds all non-dead entities within euclidean radius of pos using chunk index."""
        px, py, pz = pos
        r_sq = radius * radius
        # Chunk bounds must be floored, not truncated: int(-0.5) is 0 while
        # math.floor(-0.5) is -1, so truncating dropped the whole -1 bucket from
        # the scan and every entity just west/north of the origin became invisible
        # to merges, projectile hits and mob target acquisition.
        min_cx = math.floor(px - radius) >> 4
        max_cx = math.floor(px + radius) >> 4
        min_cz = math.floor(pz - radius) >> 4
        max_cz = math.floor(pz + radius) >> 4

        res: List[Entity] = []
        for cx in range(min_cx, max_cx + 1):
            for cz in range(min_cz, max_cz + 1):
                bucket = self.chunk_index.get((cx, cz))
                if not bucket:
                    continue
                for e in bucket:
                    if e.dead:
                        continue
                    ex, ey, ez = e.pos
                    if (ex - px) ** 2 + (ey - py) ** 2 + (ez - pz) ** 2 <= r_sq:
                        res.append(e)
        return res

    def drop_item(
        self,
        pos: Tuple[float, float, float],
        item_key: str,
        count: int = 1,
        motion: Optional[Tuple[float, float, float]] = None,
        now: Optional[float] = None,
    ) -> bool:
        """Drops an item entity in the world, merging with nearby matching stacks if possible."""
        from ..world.blocks import ITEM_RUNTIME
        from ..player.inventory import MAX_STACK

        if item_key not in ITEM_RUNTIME:
            return False
        count = int(count)
        if count <= 0:
            return False

        now = time.time() if now is None else now
        px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])

        # Merge into nearby matching stacks first, but never past the stack limit - an
        # unbounded merge is what let a single entity hold an arbitrary count, which the
        # pickup path would then duplicate. Anything that does not fit stays behind.
        for e in self.entities_near((px, py, pz), radius=MERGE_RANGE):
            if count <= 0:
                break
            if not isinstance(e, ItemEntity) or e.item_key != item_key or e.dead:
                continue
            room = MAX_STACK - e.count
            if room <= 0:
                continue
            absorbed = min(room, count)
            e.count += absorbed
            count -= absorbed
            e.age = 0.0
            e.spawned_at = now
            e.pickup_at = now + PICKUP_DELAY
        if count <= 0:
            return True

        # A single entity never holds more than one stack: otherwise pickup accounting
        # would have to hand out partial stacks that no client expects.
        spawned_any = False
        while count > 0:
            take = min(count, MAX_STACK)
            count -= take
            rand_motion = motion or (
                random.random() * 0.2 - 0.1,
                0.2,
                random.random() * 0.2 - 0.1,
            )
            if (
                self.spawn(
                    ItemEntity,
                    item_key,
                    take,
                    pos=(px, py, pz),
                    motion=rand_motion,
                    spawned_at=now,
                )
                is None
            ):
                # A plugin vetoed EntitySpawnEvent. Whatever already landed in the world
                # is real and has to be paid for, so the refusal ends the drop instead of
                # letting the caller keep items that are already lying on the ground.
                break
            spawned_any = True
        return spawned_any

    def tick(
        self, now: float, dt: float, world_is_solid: Callable[[int, int, int], bool]
    ) -> None:
        """Ticks all entities in chunks within simulation distance (4 chunks) of active players."""
        players = self.srv.playing() if hasattr(self.srv, "playing") else []
        active_chunks: Set[Tuple[int, int]] = set()

        for p in players:
            pos = getattr(p, "pos", None)
            if pos is None:
                continue
            pcx = math.floor(pos[0]) >> 4
            pcz = math.floor(pos[2]) >> 4
            for dx in range(-4, 5):
                for dz in range(-4, 5):
                    active_chunks.add((pcx + dx, pcz + dz))

        to_tick: Set[Entity] = set()
        for chunk in active_chunks:
            bucket = self.chunk_index.get(chunk)
            if bucket:
                to_tick.update(bucket)

        if not to_tick:
            return

        from ..packets.entity import build_move_actor_absolute, build_move_entity
        from ..protocol.packet_ids import PID_MOVE_ACTOR_ABSOLUTE
        from ..player.session import Session
        from ..world.blocks import ITEM_RUNTIME
        from ..player.inventory import add_item, item_tuple

        move_pkts = []
        for e in list(to_tick):
            if e.dead:
                self.remove(e.rid)
                continue

            old_chunk = e.chunk
            moved = e.tick(now, dt, world_is_solid)
            if e.dead:
                self.remove(e.rid)
                continue

            if moved:
                new_chunk = e.chunk
                if new_chunk != old_chunk:
                    if old_chunk in self.chunk_index:
                        self.chunk_index[old_chunk].discard(e)
                        if not self.chunk_index[old_chunk]:
                            del self.chunk_index[old_chunk]
                    if new_chunk not in self.chunk_index:
                        self.chunk_index[new_chunk] = set()
                    self.chunk_index[new_chunk].add(e)

                if hasattr(self.srv, "broadcast"):
                    if isinstance(e, ItemEntity):
                        move_pkts.append(
                            Session._pk(
                                PID_MOVE_ACTOR_ABSOLUTE,
                                build_move_entity(e.rid, e.pos),
                            )
                        )
                    else:
                        move_pkts.append(
                            Session._pk(
                                PID_MOVE_ACTOR_ABSOLUTE,
                                build_move_actor_absolute(e),
                            )
                        )

            # Check item pickup for ItemEntity
            if isinstance(e, ItemEntity):
                # An item key with no runtime id can never be handed to a player, so
                # resolve it once per entity instead of per player: an early exit from
                # the player loop used to make the whole item look like a hard stop.
                item_id = ITEM_RUNTIME.get(e.item_key)
                if item_id is None:
                    continue
                for p in players:
                    if not e.can_pickup(p.feet(), now, world_is_solid):
                        continue
                    # add_item already writes the slots it managed to fill, so the only
                    # correct bookkeeping is to remove exactly what was inserted. Treating
                    # a partial insert as "player full" left the whole stack in the world
                    # and gave the player a copy of it.
                    left = add_item(p.inventory, item_tuple(item_id, e.count, 0))
                    taken = e.count - left
                    if taken <= 0:
                        continue
                    e.count = left
                    p.sync_inventory()
                    if e.count <= 0:
                        self.remove(e.rid)
                    # Whatever did not fit stays in the world for the next attempt.
                    break

        if move_pkts and hasattr(self.srv, "broadcast"):
            self.srv.broadcast(move_pkts)
