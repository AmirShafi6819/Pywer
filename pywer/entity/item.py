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


def has_line_of_sight(fx, fy, fz, tx, ty, tz, world_is_solid, samples=6):
    """Rough line of sight check so items are not picked up through walls."""
    for i in range(1, samples):
        t = i / float(samples)
        if world_is_solid(
            math.floor(fx + (tx - fx) * t),
            math.floor(fy + (ty - fy) * t),
            math.floor(fz + (tz - fz) * t),
        ):
            return False
    return True


class ItemEntity(Entity):
    """Dropped item stack in world."""

    def __init__(
        self,
        srv,
        rid,
        item_key,
        count=1,
        pos=(0.0, 0.0, 0.0),
        motion=(0.0, 0.0, 0.0),
        spawned_at=0.0,
    ):
        super().__init__(srv, rid, pos, motion)
        self.item_key = item_key
        self.count = int(count)
        self.spawned_at = float(spawned_at)
        self.pickup_delay = PICKUP_DELAY
        self.pickup_at = self.spawned_at + PICKUP_DELAY
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

        # Walls: kill only blocked axis so item slides along instead of tunneling
        if solid_at(nx, y, z):
            vx = 0.0
            nx = x
        if solid_at(x, y, nz):
            vz = 0.0
            nz = z

        # Floor / ceiling
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

    def can_pickup(self, player_feet, now, world_is_solid=None):
        if now < self.pickup_at or self.dead:
            return False
        px, py, pz = player_feet
        dx = self.pos[0] - px
        dy = self.pos[1] - py
        dz = self.pos[2] - pz
        if (dx * dx + dy * dy + dz * dz) > (PICKUP_RANGE * PICKUP_RANGE):
            return False
        if world_is_solid is not None and not has_line_of_sight(
            px, py + 0.9, pz, self.pos[0], self.pos[1], self.pos[2], world_is_solid
        ):
            return False
        return True
