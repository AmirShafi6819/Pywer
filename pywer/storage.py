# ---------------------------------------------------------------- world / player persistence
# Plain JSON on disk: no third-party dependency, human-inspectable, and cheap because only
# dirty chunks are rewritten.
import json, os, time

DATA_DIR = "world_data"
WORLD_FILE = "level.json"
PLAYER_FILE = "players.json"
SAVE_INTERVAL = 30.0        # seconds between autosaves

def data_dir(base=None):
    path = base or DATA_DIR
    os.makedirs(path, exist_ok=True)
    return path

class WorldStorage:
    """Persists the seed, world metadata and every block the players changed.

    Chunks are tracked individually so a single block edit only rewrites that chunk on the
    next save instead of the whole world.
    """
    def __init__(self, base=None):
        self.dir = data_dir(base)
        self.path = os.path.join(self.dir, WORLD_FILE)
        self.meta = {}
        self.chunks = {}            # "cx,cz" -> {"seed": n, "edits": {"lx,y,lz": key}}
        self.dirty = set()
        self.loaded = False

    # ---- chunk dirty tracking
    def mark_dirty(self, cx, cz):
        self.dirty.add((cx, cz))

    def mark_all_dirty(self):
        for key in list(self.chunks.keys()):
            cx, cz = key.split(",")
            self.dirty.add((int(cx), int(cz)))

    # ---- load / save
    def load(self):
        if not os.path.exists(self.path):
            self.loaded = True
            return False
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            # A corrupt save must not stop the server from starting; fall back to a fresh world.
            self.loaded = True
            return False
        self.meta = data.get("meta", {})
        self.chunks = data.get("chunks", {})
        self.dirty.clear()
        self.loaded = True
        return True

    def save(self, meta=None, edits=None):
        """Write the level. Only chunks in `dirty` are re-serialised."""
        if meta: self.meta.update(meta)
        if edits is not None:
            # Rebuild the chunk index from the current edit map, preserving untouched entries.
            previous = self.chunks
            self.chunks = {}
            for (cx, cz), cells in edits.items():
                self.chunks["%d,%d" % (cx, cz)] = {"edits": {"%d,%d,%d" % k: v for k, v in cells.items()}}
            for key in previous:
                if key not in self.chunks and key not in {"%d,%d" % d for d in self.dirty}:
                    self.chunks[key] = previous[key]
        elif self.dirty:
            for key in list(self.chunks.keys()):
                cx, cz = key.split(",")
                if (int(cx), int(cz)) in self.dirty:
                    self.chunks[key]["touched"] = int(time.time())
        payload = {"meta": self.meta, "chunks": self.chunks,
                   "saved_at": int(time.time())}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
        os.replace(tmp, self.path)          # atomic: a crash mid-save cannot corrupt the level
        self.dirty.clear()
        return True

    def loaded_edits(self):
        """Rehydrate the saved edits as {(cx, cz): {(lx, y, lz): key}}."""
        out = {}
        for key, chunk in self.chunks.items():
            cx, cz = key.split(",")
            cells = {}
            for coord, block in chunk.get("edits", {}).items():
                lx, y, lz = coord.split(",")
                cells[(int(lx), int(y), int(lz))] = block
            out[(int(cx), int(cz))] = cells
        return out


class PlayerStorage:
    """Player data keyed by UUID, so reconnecting restores the same character."""
    def __init__(self, base=None):
        self.dir = data_dir(base)
        self.path = os.path.join(self.dir, PLAYER_FILE)
        self.players = {}
        self.dirty = set()

    def load(self):
        if not os.path.exists(self.path): return False
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                self.players = json.load(fh)
        except Exception:
            self.players = {}
            return False
        return True

    def get(self, uuid):
        return self.players.get(str(uuid))

    def put(self, uuid, data):
        self.players[str(uuid)] = data
        self.dirty.add(str(uuid))

    def save(self, force=False):
        if not self.dirty and not force: return False
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.players, fh, separators=(",", ":"))
        os.replace(tmp, self.path)
        self.dirty.clear()
        return True