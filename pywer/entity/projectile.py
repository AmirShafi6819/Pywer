"""Projectile entities: arrows, snowballs, and trajectory physics."""

import math
from .base import Entity


class Projectile(Entity):
    """Base class for ranged projectiles."""

    def __init__(
        self,
        srv,
        rid,
        shooter_rid=None,
        pos=(0.0, 0.0, 0.0),
        motion=(0.0, 0.0, 0.0),
        damage=0.0,
        knockback=0.4,
        gravity=0.03,
        drag=0.01,
    ):
        super().__init__(srv, rid, pos, motion)
        self.shooter_rid = shooter_rid
        self.damage = float(damage)
        self.knockback = float(knockback)
        self.gravity = float(gravity)
        self.drag = float(drag)
        self.in_ground = False
        self.life_ticks = 0

    def stick_in_ground(self):
        self.in_ground = True
        self.motion = (0.0, 0.0, 0.0)

    def tick(self, now, dt, world_is_solid):
        if self.in_ground:
            self.life_ticks += 1
            if self.life_ticks >= 1200:  # 60 seconds
                self.dead = True
            return False

        vx, vy, vz = self.motion
        vy -= self.gravity
        vx *= (1.0 - self.drag)
        vz *= (1.0 - self.drag)
        self.motion = (vx, vy, vz)

        x, y, z = self.pos
        nx, ny, nz = x + vx, y + vy, z + vz
        self.pos = (nx, ny, nz)

        # Update look orientation from velocity vector
        horiz_speed = math.hypot(vx, vz)
        if horiz_speed > 0.001 or abs(vy) > 0.001:
            self.yaw = math.degrees(math.atan2(-vx, vz))
            self.pitch = -math.degrees(math.atan2(vy, horiz_speed))
            self.head_yaw = self.yaw

        return True


class Arrow(Projectile):
    """Fired arrow entity."""

    def __init__(
        self,
        srv,
        rid,
        shooter_rid=None,
        pos=(0.0, 0.0, 0.0),
        motion=(0.0, 0.0, 0.0),
        damage=4.0,
    ):
        super().__init__(
            srv,
            rid,
            shooter_rid=shooter_rid,
            pos=pos,
            motion=motion,
            damage=damage,
            knockback=0.4,
            gravity=0.05,
            drag=0.01,
        )
        self.identifier = "minecraft:arrow"
        self.width = 0.25
        self.height = 0.25


class Snowball(Projectile):
    """Thrown snowball entity."""

    def __init__(
        self,
        srv,
        rid,
        shooter_rid=None,
        pos=(0.0, 0.0, 0.0),
        motion=(0.0, 0.0, 0.0),
    ):
        super().__init__(
            srv,
            rid,
            shooter_rid=shooter_rid,
            pos=pos,
            motion=motion,
            damage=0.0,
            knockback=0.3,
            gravity=0.03,
            drag=0.01,
        )
        self.identifier = "minecraft:snowball"
        self.width = 0.25
        self.height = 0.25
