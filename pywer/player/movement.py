# ---------------------------------------------------------------- player movement (PocketMine-MP 5.22.0 port)
# Reverse engineered from: InGamePacketHandler::handlePlayerAuthInput, Player::handleMovement /
# actuallyHandleMovement / processMostRecentMovements / revertMovement / toggle*, NetworkSession::syncMovement,
# Entity::broadcastMovement + BedrockProtocol PlayerAuthInputPacket / PlayerAuthInputFlags / MovePlayerPacket /
# MoveActorAbsolutePacket / SetActorDataPacket (1.21.50, protocol 766).
import math
from .. import config
from ..world.query import is_solid

EYE_HEIGHT = 1.62
NETWORK_EYE_OFFSET = 1.621  # Human::getOffsetPosition() in PocketMine-MP 5.22.0
MOVES_PER_TICK = 2; MOVE_BACKLOG_SIZE = 100 * MOVES_PER_TICK       # Player.php: rate limit (100 ticks backlog)
MAX_MOVE_DISTANCE_SQ = 225                                         # 15 blocks, Player::actuallyHandleMovement
ALLOW_FLIGHT = config.GAMEMODE in (1, 6)                            # creative / spectator, like Player::$allowFlight
MODE_NORMAL, MODE_RESET, MODE_TELEPORT = 0, 1, 2                   # MovePlayerPacket::MODE_*
MOVE_FLAG_GROUND = 0x01                                            # MoveActorAbsolutePacket::FLAG_GROUND

def _finite(*vals): return all(not (math.isnan(v) or math.isinf(v)) for v in vals)

def player_size(p):
    """Living::recalculateSize: (width, height)."""
    if p.swimming or p.gliding: return 0.6, 0.6
    if p.sneaking: return 0.6, 1.8 * 0.75
    return 0.6, 1.8

# PocketMine-style entity collision -------------------------------------------------
# Entity::move() resolves Y first, then X, then Z against block AABBs. Player has a
# 0.6 x 1.8 collision box and a 0.6 step height. This is deliberately kept local
# and deterministic because our world blocks are all unit cubes.
PLAYER_STEP_HEIGHT = 0.6

def _block_collision_boxes(bb_min_x, bb_min_y, bb_min_z, bb_max_x, bb_max_y, bb_max_z):
    """Yield unit-cube AABBs for solid blocks intersecting the swept region."""
    if not config.TERRAIN:
        return []
    x0 = math.floor(bb_min_x); x1 = math.floor(bb_max_x - 1e-9)
    y0 = math.floor(bb_min_y); y1 = math.floor(bb_max_y - 1e-9)
    z0 = math.floor(bb_min_z); z1 = math.floor(bb_max_z - 1e-9)
    out = []
    # Keep the search bounded. Entity::move() in PM asserts each requested delta <= 20.
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            for z in range(z0, z1 + 1):
                if is_solid(x, y, z):
                    out.append((x, y, z, x + 1.0, y + 1.0, z + 1.0))
    return out

def _calc_y_offset(box, dy, other):
    minx,miny,minz,maxx,maxy,maxz = box; ox0,oy0,oz0,ox1,oy1,oz1 = other
    if ox1 <= minx or ox0 >= maxx or oz1 <= minz or oz0 >= maxz: return dy
    if dy > 0.0 and maxy <= oy0 + 1e-12:
        d = oy0 - maxy
        if d < dy: dy = d
    elif dy < 0.0 and miny >= oy1 - 1e-12:
        d = oy1 - miny
        if d > dy: dy = d
    return dy

def _calc_x_offset(box, dx, other):
    minx,miny,minz,maxx,maxy,maxz = box; ox0,oy0,oz0,ox1,oy1,oz1 = other
    if oy1 <= miny or oy0 >= maxy or oz1 <= minz or oz0 >= maxz: return dx
    if dx > 0.0 and maxx <= ox0 + 1e-12:
        d = ox0 - maxx
        if d < dx: dx = d
    elif dx < 0.0 and minx >= ox1 - 1e-12:
        d = ox1 - minx
        if d > dx: dx = d
    return dx

def _calc_z_offset(box, dz, other):
    minx,miny,minz,maxx,maxy,maxz = box; ox0,oy0,oz0,ox1,oy1,oz1 = other
    if ox1 <= minx or ox0 >= maxx or oy1 <= miny or oy0 >= maxy: return dz
    if dz > 0.0 and maxz <= oz0 + 1e-12:
        d = oz0 - maxz
        if d < dz: dz = d
    elif dz < 0.0 and minz >= oz1 - 1e-12:
        d = oz1 - minz
        if d > dz: dz = d
    return dz

def _offset_box(box, dx, dy, dz):
    a,b,c,d,e,f = box
    return (a+dx,b+dy,c+dz,d+dx,e+dy,f+dz)

def _move_with_collision(p, wanted_dx, wanted_dy, wanted_dz):
    """Port of Entity::move() for Player-sized unit-block terrain."""
    w,h = player_size(p); hw = w / 2.0
    fx,fy,fz = p.feet()
    box = (fx-hw, fy, fz-hw, fx+hw, fy+h, fz+hw)

    # PM expands the queried collision region by the requested movement, then
    # resolves vertical, horizontal-X, and horizontal-Z independently.
    sx0 = min(box[0], box[0] + wanted_dx); sx1 = max(box[3], box[3] + wanted_dx)
    sy0 = min(box[1], box[1] + wanted_dy); sy1 = max(box[4], box[4] + wanted_dy)
    sz0 = min(box[2], box[2] + wanted_dz); sz1 = max(box[5], box[5] + wanted_dz)
    boxes = _block_collision_boxes(sx0, sy0, sz0, sx1, sy1, sz1)

    dx,dy,dz = wanted_dx,wanted_dy,wanted_dz
    for b in boxes: dy = _calc_y_offset(box, dy, b)
    box = _offset_box(box, 0, dy, 0)
    falling = p.on_ground or (dy != wanted_dy and wanted_dy < 0.0)

    for b in boxes: dx = _calc_x_offset(box, dx, b)
    box = _offset_box(box, dx, 0, 0)
    for b in boxes: dz = _calc_z_offset(box, dz, b)
    box = _offset_box(box, 0, 0, dz)

    # Player::move() attempts a step-up when grounded/falling and horizontal
    # motion was blocked. It keeps whichever path travels farther horizontally.
    if PLAYER_STEP_HEIGHT > 0 and falling and (wanted_dx != dx or wanted_dz != dz):
        cx,cy,cz = dx,dy,dz
        sbox = (fx-hw, fy, fz-hw, fx+hw, fy+h, fz+hw)
        sdx,sdy,sdz = wanted_dx,PLAYER_STEP_HEIGHT,wanted_dz
        ssx0=min(sbox[0],sbox[0]+sdx); ssx1=max(sbox[3],sbox[3]+sdx)
        ssy0=min(sbox[1],sbox[1]+sdy); ssy1=max(sbox[4],sbox[4]+sdy)
        ssz0=min(sbox[2],sbox[2]+sdz); ssz1=max(sbox[5],sbox[5]+sdz)
        step_boxes=_block_collision_boxes(ssx0,ssy0,ssz0,ssx1,ssy1,ssz1)
        for b in step_boxes: sdy=_calc_y_offset(sbox,sdy,b)
        sbox=_offset_box(sbox,0,sdy,0)
        for b in step_boxes: sdx=_calc_x_offset(sbox,sdx,b)
        sbox=_offset_box(sbox,sdx,0,0)
        for b in step_boxes: sdz=_calc_z_offset(sbox,sdz,b)
        sbox=_offset_box(sbox,0,0,sdz)
        reverse_dy=-sdy
        for b in step_boxes: reverse_dy=_calc_y_offset(sbox,reverse_dy,b)
        sdy += reverse_dy
        sbox=_offset_box(sbox,0,reverse_dy,0)
        if cx*cx + cz*cz < sdx*sdx + sdz*sdz:
            dx,dy,dz = sdx,sdy,sdz
            box=sbox

    new_feet=( (box[0]+box[3])/2.0, box[1], (box[2]+box[5])/2.0 )
    collided_y = (wanted_dy != dy)
    # PocketMine re-checks a thin box around the new position to determine onGround,
    # including horizontal movement across a flat surface (important when dy == 0).
    ground_box = (box[0], box[1] - 0.20, box[2], box[3], box[1] + 0.20, box[5])
    grounded = False
    for b in _block_collision_boxes(*ground_box):
        if b[4] > box[1] - 1e-6 and b[4] <= box[1] + 0.20 + 1e-6 and b[0] < box[3] and b[3] > box[0] and b[2] < box[5] and b[5] > box[2]:
            grounded = True; break
    p.on_ground = bool((collided_y and wanted_dy < 0.0) or grounded)
    return new_feet, (dx,dy,dz)