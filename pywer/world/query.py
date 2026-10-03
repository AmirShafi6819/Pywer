# ---- block lookup (collision): edits > trees > terrain layers
from .. import config
from .terrain import tree_blocks, column_layers
from .state import EDITS

_TREE_CACHE = {}
def get_block(x, y, z):
    if y < config.MIN_Y or y > config.MAX_Y: return "air"
    cx, cz = x >> 4, z >> 4
    k = EDITS.get((cx, cz), {}).get((x & 15, y, z & 15))
    if k is not None: return k
    if config.TREES:
        tb = _TREE_CACHE.get((cx, cz))
        if tb is None:
            if len(_TREE_CACHE) > 512: _TREE_CACHE.clear()
            tb = _TREE_CACHE[(cx, cz)] = tree_blocks(cx, cz)
        k = tb.get((x, y, z))
        if k is not None: return k
    key = "air"
    for y0, y1, bk in column_layers(x, z):
        if y0 <= y <= y1: key = bk
    return key
def is_solid(x, y, z): return get_block(x, y, z) not in ("air", "water")