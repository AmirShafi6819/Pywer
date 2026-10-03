"""Physics engine routines for discrete raycasting and collision detection.

Prevents tunneling for fast-moving projectiles and provides spatial intersection
tests against solid voxel terrain and entity axis-aligned bounding boxes (AABBs).
"""

import math
from typing import Any, Callable, Iterable, Optional, Tuple


def raycast_step(
    start_pos: Tuple[float, float, float],
    motion: Tuple[float, float, float],
    world_is_solid: Callable[[int, int, int], bool],
    step_size: float = 0.25,
) -> Tuple[str, Tuple[float, float, float], Optional[Tuple[int, int, int]], Optional[int]]:
    """Sub-steps along motion vector to find first voxel intersection.

    Returns:
        (hit_type, hit_pos, block_pos, face)
        - hit_type: 'block' or 'none'
        - hit_pos: (x, y, z) contact point
        - block_pos: (bx, by, bz) of the hit block or None
        - face: Bedrock face index (0: Down, 1: Up, 2: North, 3: South, 4: West, 5: East) or None
    """
    ox, oy, oz = start_pos
    vx, vy, vz = motion
    length = math.sqrt(vx * vx + vy * vy + vz * vz)

    if length < 1e-6:
        return "none", (ox, oy, oz), None, None

    num_steps = max(1, math.ceil(length / step_size))
    prev_bx = math.floor(ox)
    prev_by = math.floor(oy)
    prev_bz = math.floor(oz)

    for i in range(1, num_steps + 1):
        t = i / float(num_steps)
        cx = ox + vx * t
        cy = oy + vy * t
        cz = oz + vz * t

        bx = math.floor(cx)
        by = math.floor(cy)
        bz = math.floor(cz)

        if world_is_solid(bx, by, bz):
            # Determine which face was struck based on step direction
            if bx > prev_bx:
                face = 4  # Hit West (-x) face
            elif bx < prev_bx:
                face = 5  # Hit East (+x) face
            elif by > prev_by:
                face = 0  # Hit Down (-y) face
            elif by < prev_by:
                face = 1  # Hit Up (+y) face
            elif bz > prev_bz:
                face = 2  # Hit North (-z) face
            elif bz < prev_bz:
                face = 3  # Hit South (+z) face
            else:
                # Same block or step 1: infer face from dominant motion axis
                if abs(vy) >= abs(vx) and abs(vy) >= abs(vz):
                    face = 1 if vy < 0 else 0
                elif abs(vx) >= abs(vz):
                    face = 4 if vx > 0 else 5
                else:
                    face = 2 if vz > 0 else 3

            return "block", (cx, cy, cz), (bx, by, bz), face

        prev_bx, prev_by, prev_bz = bx, by, bz

    return "none", (ox + vx, oy + vy, oz + vz), None, None


def ray_aabb_intersection_dist(
    aabb: Tuple[float, float, float, float, float, float],
    start_pos: Tuple[float, float, float],
    motion: Tuple[float, float, float],
) -> Optional[float]:
    """Calculates entry parameter t in [0.0, 1.0] if ray intersects AABB, else None."""
    min_x, min_y, min_z, max_x, max_y, max_z = aabb
    ox, oy, oz = start_pos
    dx, dy, dz = motion

    t_min = 0.0
    t_max = 1.0

    axes = (
        (ox, dx, min_x, max_x),
        (oy, dy, min_y, max_y),
        (oz, dz, min_z, max_z),
    )

    for o, d, min_val, max_val in axes:
        if abs(d) < 1e-9:
            if o < min_val or o > max_val:
                return None
        else:
            inv_d = 1.0 / d
            t1 = (min_val - o) * inv_d
            t2 = (max_val - o) * inv_d
            if t1 > t2:
                t1, t2 = t2, t1
            t_min = max(t_min, t1)
            t_max = min(t_max, t2)
            if t_min > t_max:
                return None

    if t_max < 0.0 or t_min > 1.0:
        return None

    return t_min


def aabb_intersects_ray(
    aabb: Tuple[float, float, float, float, float, float],
    start_pos: Tuple[float, float, float],
    motion: Tuple[float, float, float],
) -> bool:
    """Tests if a line segment (start_pos -> start_pos + motion) intersects an AABB."""
    return ray_aabb_intersection_dist(aabb, start_pos, motion) is not None


def check_projectile_collisions(
    projectile: Any,
    nearby_entities: Iterable[Any],
    world_is_solid: Callable[[int, int, int], bool],
) -> Tuple[str, Any, Tuple[float, float, float]]:
    """Evaluates collisions along projectile's trajectory for both entities and blocks.

    Returns:
        (hit_type, target_or_block, hit_pos)
        - hit_type: 'entity', 'block', or 'none'
        - target_or_block: Entity if entity hit; ((bx, by, bz), face) if block hit; None if none
        - hit_pos: (x, y, z) intersection coordinates
    """
    start_pos = projectile.pos
    motion = projectile.motion

    # 1. Test entity collisions along motion vector
    closest_entity = None
    closest_entity_t = 2.0
    closest_entity_hit_pos = None

    for ent in nearby_entities:
        if ent is projectile or ent.dead:
            continue
        # Immunity for shooter during the first 0.25s (approx 5 ticks)
        if getattr(projectile, "shooter_rid", None) is not None:
            if ent.rid == projectile.shooter_rid and getattr(projectile, "age", 0.0) < 0.25:
                continue

        t_hit = ray_aabb_intersection_dist(ent.aabb(), start_pos, motion)
        if t_hit is not None and t_hit < closest_entity_t:
            closest_entity_t = t_hit
            closest_entity = ent
            closest_entity_hit_pos = (
                start_pos[0] + motion[0] * t_hit,
                start_pos[1] + motion[1] * t_hit,
                start_pos[2] + motion[2] * t_hit,
            )

    # 2. Test terrain block collisions
    block_hit_type, block_hit_pos, block_pos, face = raycast_step(
        start_pos, motion, world_is_solid
    )

    if block_hit_type == "block":
        # Calculate t along motion vector for block hit
        dx = block_hit_pos[0] - start_pos[0]
        dy = block_hit_pos[1] - start_pos[1]
        dz = block_hit_pos[2] - start_pos[2]
        motion_len_sq = motion[0] ** 2 + motion[1] ** 2 + motion[2] ** 2
        block_t = math.sqrt(dx * dx + dy * dy + dz * dz) / math.sqrt(motion_len_sq) if motion_len_sq > 0 else 0.0

        if closest_entity is not None and closest_entity_t <= block_t:
            return "entity", closest_entity, closest_entity_hit_pos
        return "block", (block_pos, face), block_hit_pos

    if closest_entity is not None:
        return "entity", closest_entity, closest_entity_hit_pos

    return "none", None, block_hit_pos
