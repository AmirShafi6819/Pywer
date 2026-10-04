"""Living entities and non-player mobs (passive and hostile)."""

import math
import random
from .base import Entity


class LivingEntity(Entity):
    """Base class for actors with health, damage, and attributes."""

    def __init__(
        self,
        srv,
        rid,
        pos=(0.0, 0.0, 0.0),
        motion=(0.0, 0.0, 0.0),
        health=20.0,
        max_health=20.0,
    ):
        super().__init__(srv, rid, pos, motion)
        self.health = float(health)
        self.max_health = float(max_health)
        self.hurt_time = 0

    def damage(self, amount, attacker=None, source_rid=None, cause=None):
        """Entity::attack pipeline for non-player living entities.

        The signature matches Session.damage on purpose: `Server.handle_entity_attack`
        has one `target` variable that may hold either kind of actor, and passing a
        session positionally used to land in `source_rid`, where a Session was compared
        against integer rids, matched nothing, and the hit arrived as a bare
        EntityDamageEvent with no damager and no knockback.
        """
        from ..event import EntityDamageByEntityEvent, EntityDamageEvent
        from ..event import manager as events
        from .manager import resolve_actor

        if self.dead or self.hurt_time > 0:
            return False
        amount = float(amount)
        # Zero-damage impacts (snowball, egg) must still dispatch the event and play
        # the hurt animation; only a negative amount is meaningless.
        if amount < 0.0:
            return False
        if attacker is None and source_rid is not None:
            attacker = resolve_actor(self.srv, source_rid)
        if cause is None:
            cause = (
                "entity_attack"
                if (attacker is not None or source_rid is not None)
                else "generic"
            )
        ev = (
            EntityDamageByEntityEvent(self, attacker, amount, cause)
            if attacker is not None
            else EntityDamageEvent(self, amount, cause)
        )
        events.call(ev)
        if ev.is_cancelled:
            return False
        amount = float(ev.amount)
        if amount < 0.0:
            return False
        self.health = max(0.0, self.health - amount)
        self.hurt_time = 10
        self.broadcast_damage()
        if self.health <= 0.0:
            self.dead = True
        return True

    def broadcast_damage(self):
        """Push the hurt animation and the new health to every client.

        Nothing told the clients a mob had been hit: the ActorEvent never went out and
        the attributes packet was only ever built for players. Both packets go out in
        one broadcast - two calls would deflate and hand off two RakNet datagrams to
        every connected client for a single event.
        """
        if not hasattr(self.srv, "broadcast"):
            return
        from ..packets.entity import build_actor_event, build_update_attributes
        from ..player.session import ANIMATE_ACTION_HURT, Session
        from ..protocol.packet_ids import PID_ACTOR_EVENT, PID_UPDATE_ATTRIBUTES

        self.srv.broadcast(
            [
                Session._pk(PID_ACTOR_EVENT, build_actor_event(self.rid, ANIMATE_ACTION_HURT)),
                Session._pk(PID_UPDATE_ATTRIBUTES, build_update_attributes(self)),
            ]
        )

    def tick_living(self):
        if self.hurt_time > 0:
            self.hurt_time -= 1


class Mob(LivingEntity):
    """Living entity with basic AI state machine."""

    def __init__(
        self,
        srv,
        rid,
        pos=(0.0, 0.0, 0.0),
        motion=(0.0, 0.0, 0.0),
        health=20.0,
        max_health=20.0,
        speed=0.1,
    ):
        super().__init__(srv, rid, pos, motion, health, max_health)
        self.ai_state = "IDLE"
        self.speed = float(speed)
        self.target_player = None


class Zombie(Mob):
    """Hostile zombie mob."""

    def __init__(self, srv, rid, pos=(0.0, 0.0, 0.0)):
        super().__init__(
            srv,
            rid,
            pos=pos,
            health=20.0,
            max_health=20.0,
            speed=0.2,
        )
        self.identifier = "minecraft:zombie"
        self.width = 0.6
        self.height = 1.9
        self.attack_damage = 3.0

    def tick(self, now, dt, world_is_solid):
        self.tick_living()
        if self.dead:
            return False

        # Find nearest non-creative player within 16 blocks
        nearest_p = None
        min_dist_sq = 16.0 * 16.0
        x, y, z = self.pos

        if hasattr(self.srv, "playing"):
            for p in self.srv.playing():
                if hasattr(p, "gamemode_is_creative") and p.gamemode_is_creative():
                    continue
                pf = p.feet()
                dx = pf[0] - x
                dy = pf[1] - y
                dz = pf[2] - z
                dsq = dx * dx + dy * dy + dz * dz
                if dsq < min_dist_sq:
                    min_dist_sq = dsq
                    nearest_p = p

        if nearest_p is not None:
            self.ai_state = "TARGET"
            self.target_player = nearest_p
            pf = nearest_p.feet()
            dx = pf[0] - x
            dz = pf[2] - z
            dist = math.hypot(dx, dz)
            if dist > 0.001:
                step_x = (dx / dist) * min(self.speed, dist)
                step_z = (dz / dist) * min(self.speed, dist)
                nx = x + step_x
                nz = z + step_z
                # Step up 1 block if ground block in front is solid
                ny = y
                if world_is_solid(math.floor(nx), math.floor(ny), math.floor(nz)):
                    if not world_is_solid(math.floor(nx), math.floor(ny + 1), math.floor(nz)):
                        ny += 1.0

                self.pos = (nx, ny, nz)
                self.yaw = math.degrees(math.atan2(-dx, dz))
                self.head_yaw = self.yaw

                # Attack player if within 1.5 blocks
                if dist <= 1.5 and hasattr(nearest_p, "damage"):
                    nearest_p.damage(self.attack_damage, attacker=self)
                return True
        else:
            self.ai_state = "IDLE"
            self.target_player = None

        return False


class Cow(Mob):
    """Passive cow mob."""

    def __init__(self, srv, rid, pos=(0.0, 0.0, 0.0)):
        super().__init__(
            srv,
            rid,
            pos=pos,
            health=10.0,
            max_health=10.0,
            speed=0.08,
        )
        self.identifier = "minecraft:cow"
        self.width = 0.9
        self.height = 1.4
        self.ai_state = "WANDER"
        self._wander_dir = (0.0, 0.0)
        self._wander_ticks = 0

    def tick(self, now, dt, world_is_solid):
        self.tick_living()
        if self.dead:
            return False

        self._wander_ticks += 1
        if self._wander_ticks > 40:
            self._wander_ticks = 0
            if random.random() < 0.6:
                angle = random.random() * 2 * math.pi
                self._wander_dir = (math.cos(angle) * self.speed, math.sin(angle) * self.speed)
                self.ai_state = "WANDER"
            else:
                self._wander_dir = (0.0, 0.0)
                self.ai_state = "IDLE"

        vx, vz = self._wander_dir
        if vx != 0.0 or vz != 0.0:
            x, y, z = self.pos
            nx = x + vx
            nz = z + vz
            if not world_is_solid(math.floor(nx), math.floor(y), math.floor(nz)):
                self.pos = (nx, y, nz)
                self.yaw = math.degrees(math.atan2(-vx, vz))
                self.head_yaw = self.yaw
                return True

        return False
