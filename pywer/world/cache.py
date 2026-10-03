"""Thread-safe in-memory cache for pre-built chunk payloads."""

import threading


class ChunkCache:
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, cx, cz):
        """Retrieve pre-built binary chunk payload if cached."""
        with self._lock:
            return self._cache.get((cx, cz))

    def put(self, cx, cz, payload):
        """Store pre-built binary chunk payload."""
        with self._lock:
            self._cache[(cx, cz)] = payload

    def invalidate(self, cx, cz):
        """Evict a chunk from cache."""
        with self._lock:
            self._cache.pop((cx, cz), None)

    def invalidate_block(self, x, z):
        """Evict the chunk containing block coordinates (x, z)."""
        cx = int(x) >> 4
        cz = int(z) >> 4
        self.invalidate(cx, cz)

    def clear(self):
        """Clear all cached chunks."""
        with self._lock:
            self._cache.clear()

    def __len__(self):
        with self._lock:
            return len(self._cache)
