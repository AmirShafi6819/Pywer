"""Base class for all non-player world actors."""

import math


class Entity:
    """Base class for all non-player world actors."""

    def __init__(
        self,
        srv,
        rid,
        pos=(0.0, 0.0, 0.0),
        motion=(0.0, 0.0, 0.0),
        pitch=0.0,
        yaw=0.0,
    ):
        self.srv = srv
        self.rid = int(rid)
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
        # Floor, not truncation: int(-0.5) is 0, which would bucket an entity just west
        # of the origin into chunk 0 instead of -1 and disagree with the player's own
        # chunk maths (Session uses math.floor too).
        return (math.floor(self.pos[0]) >> 4, math.floor(self.pos[2]) >> 4)

    def feet(self):
        """Feet/base position for actor packets."""
        return self.pos

    def aabb(self):
        """Bounding box: (min_x, min_y, min_z, max_x, max_y, max_z)."""
        hw = self.width / 2.0
        return (
            self.pos[0] - hw,
            self.pos[1],
            self.pos[2] - hw,
            self.pos[0] + hw,
            self.pos[1] + self.height,
            self.pos[2] + hw,
        )

    def tick(self, now, dt, world_is_solid):
        """Advance entity state by dt seconds. Returns True if position changed."""
        raise NotImplementedError
