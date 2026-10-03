# ---------------------------------------------------------------- dropped item entities
"""Dropped item entities: motion physics, collision bounce, line of sight, and pickup checks."""

import math

GRAVITY = 0.08  # per tick, matching Entity::gravity
HORIZONTAL_DRAG = 0.7  # air resistance on the horizontal components
GROUND_FRICTION = 0.5  # extra slowdown once item is resting on ground
PICKUP_DELAY = 0.5  # seconds before an item can be picked up
LIFETIME = 300.0  # seconds before item despawns (5 minutes)
PICKUP_RANGE = 1.5  # blocks from player feet
MERGE_RANGE = 0.75  # nearby identical stacks merge into one entity


def step_item(entity, world_is_solid):
    """Advance one item entity by one server tick.

    Plain gravity on Y, drag on X/Z, wall bounce, and a stop once item settles on ground.
    Returns True when position changed.
    """
    x, y, z = entity["pos"]
    vx, vy, vz = entity["motion"]

    def solid_at(px, py, pz):
        return world_is_solid(math.floor(px), math.floor(py), math.floor(pz))

    vy = vy - GRAVITY
    nx = x + vx
    ny = y + vy
    nz = z + vz

    # Walls: kill only the blocked axis so the item slides along instead of tunnelling.
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
    entity["pos"] = (nx, ny, nz)
    entity["motion"] = (vx, vy, vz)
    entity["resting"] = resting
    return moved


def has_line_of_sight(fx, fy, fz, tx, ty, tz, world_is_solid, samples=6):
    """Rough line of sight so items are not picked up through walls."""
    for i in range(1, samples):
        t = i / float(samples)
        if world_is_solid(
            math.floor(fx + (tx - fx) * t),
            math.floor(fy + (ty - fy) * t),
            math.floor(fz + (tz - fz) * t),
        ):
            return False
    return True


def can_pickup(entity, player_feet, now, world_is_solid=None):
    """True when item is past pickup delay and within reach of player feet."""
    if now < entity.get("pickup_at", 0.0):
        return False
    px, py, pz = player_feet
    x, y, z = entity["pos"]
    dx = x - px
    dy = y - py
    dz = z - pz
    if dx * dx + dy * dy + dz * dz > PICKUP_RANGE * PICKUP_RANGE:
        return False
    if world_is_solid is not None and not has_line_of_sight(px, py + 0.9, pz, x, y, z, world_is_solid):
        return False
    return True