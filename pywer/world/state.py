# ---- runtime world state: block edits from set_block/breaking + chunk packet cache
"""Runtime world state, dirty chunk tracker, and chunk packet cache."""

EDITS = {}  # (cx, cz) -> {(lx, y, lz): key}
CHUNK_CACHE = {}  # (cx, cz) -> LevelChunk packet body
DIRTY = set()  # (cx, cz) chunks changed since the last save


def mark_dirty(cx, cz):
    """Record a chunk as modified so the saver rewrites only what changed."""
    DIRTY.add((cx, cz))


def dirty_chunks():
    return DIRTY


def clear_dirty():
    DIRTY.clear()


def load_edits(loaded):
    """Replace the edit map with saved data."""
    EDITS.clear()
    for key, cells in loaded.items():
        EDITS[key] = dict(cells)
    CHUNK_CACHE.clear()
    clear_dirty()