# ---- terrain (deterministic value noise, so every chunk agrees with its neighbours)
import math
from .. import config

def _hash2(x, z, salt):
    n = (x * 374761393 + z * 668265263 + (config.SEED + salt) * 144665) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return (n ^ (n >> 16)) / 4294967296.0
def _vnoise(x, z, salt):
    x0 = math.floor(x); z0 = math.floor(z); fx = x - x0; fz = z - z0
    sx = fx * fx * (3 - 2 * fx); sz = fz * fz * (3 - 2 * fz)
    a = _hash2(x0, z0, salt); b = _hash2(x0 + 1, z0, salt); c = _hash2(x0, z0 + 1, salt); d = _hash2(x0 + 1, z0 + 1, salt)
    return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sz

_HEIGHT = {}
def terrain_height(x, z):
    """Y of the top solid block of column (x, z)."""
    k = (x, z); h = _HEIGHT.get(k)
    if h is None:
        v = 64 + (_vnoise(x / 96.0, z / 96.0, 1) - 0.5) * 40 + (_vnoise(x / 32.0, z / 32.0, 2) - 0.5) * 14 \
            + (_vnoise(x / 12.0, z / 12.0, 3) - 0.5) * 4
        h = int(v)
        if len(_HEIGHT) > 400000: _HEIGHT.clear()
        _HEIGHT[k] = h
    return h

def tree_at(x, z):
    """Trunk height if an oak tree is rooted at column (x, z), else 0."""
    if not config.TREES or terrain_height(x, z) <= config.SEA_LEVEL + 1: return 0
    r = _hash2(x, z, 7)
    return 4 + int(r * 1000) % 3 if r < 0.012 else 0

def column_layers(x, z):
    """Bottom-to-top list of (y0, y1, block key) for one column, without trees."""
    h = terrain_height(x, z); layers = [(config.MIN_Y, config.MIN_Y, "bedrock")]
    stone_top = h - 4
    layers.append((config.MIN_Y + 1, stone_top, "stone"))
    for i, y in enumerate((config.MIN_Y + 1, config.MIN_Y + 2, config.MIN_Y + 3), 1):         # ragged bedrock floor (drawn over the stone)
        if _hash2(x, z, 20 + i) < 0.6 - 0.2 * i: layers.append((y, y, "bedrock"))
    if h < config.SEA_LEVEL - 4:   layers += [(h - 3, h, "gravel")]
    elif h <= config.SEA_LEVEL + 1: layers += [(h - 3, h, "sand")]
    else:                    layers += [(h - 3, h - 1, "dirt"), (h, h, "grass_block")]
    if h < config.SEA_LEVEL: layers.append((h + 1, config.SEA_LEVEL, "water"))
    return layers

def tree_blocks(cx, cz):
    """{(world x, y, z): key} of every tree block that falls inside chunk (cx, cz) (trees may overhang by 2)."""
    out = {}; x0 = cx * 16; z0 = cz * 16
    for wx in range(x0 - 2, x0 + 18):
        for wz in range(z0 - 2, z0 + 18):
            th = tree_at(wx, wz)
            if not th: continue
            base = terrain_height(wx, wz)
            for dy in range(1, th + 1): out[(wx, base + dy, wz)] = "oak_log"
            for dy, rad in ((th - 1, 2), (th, 2), (th + 1, 1), (th + 2, 1)):
                for dx in range(-rad, rad + 1):
                    for dz in range(-rad, rad + 1):
                        if abs(dx) == rad and abs(dz) == rad and (rad == 2 or dy == th + 2): continue   # round the corners
                        if dx == 0 and dz == 0 and dy <= th: continue                                    # trunk
                        out[(wx + dx, base + dy, wz + dz)] = "oak_leaves"
    return {k: v for k, v in out.items() if x0 <= k[0] < x0 + 16 and z0 <= k[2] < z0 + 16 and config.MIN_Y <= k[1] <= config.MAX_Y}

def find_spawn():
    for r in range(0, 200):
        for x in range(-r, r + 1):
            for z in range(-r, r + 1):
                if max(abs(x), abs(z)) != r: continue
                h = terrain_height(x, z)
                if h > config.SEA_LEVEL + 1 and not any(tree_at(x + a, z + b) for a in range(-3, 4) for b in range(-3, 4)):
                    return (x, h + 1, z)
    return (0, config.SEA_LEVEL + 10, 0)

SPAWN = find_spawn() if config.TERRAIN else config.DEFAULT_SPAWN