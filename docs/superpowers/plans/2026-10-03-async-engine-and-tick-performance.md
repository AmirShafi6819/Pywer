# Async Engine & Tick Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple CPU-heavy terrain generation and serialization from the main server loop into background worker threads, implement non-blocking socket drainage, and achieve rock-solid 20.0 TPS timing.

**Architecture:** A thread-pool worker pipeline (`pywer.server.worker.WorkerPool`) processes terrain generation and chunk encoding off the main thread, feeding results through a thread-safe `queue.Queue`. The main loop in `pywer.server.server.Server` uses a non-blocking socket drain loop and monotonic tick pacing with `time.perf_counter()`, safely querying an in-memory `ChunkCache` with instant invalidation upon block modifications.

**Tech Stack:** Python 3.10+, `concurrent.futures.ThreadPoolExecutor`, `queue.Queue`, `time.perf_counter()`, `socket`, `select`, `unittest`.

**Spec:** [`docs/superpowers/specs/2026-10-03-async-engine-and-tick-performance-design.md`](file:///c:/Users/Mani/Desktop/Pywer/docs/superpowers/specs/2026-10-03-async-engine-and-tick-performance-design.md)

## Global Constraints
- Target Bedrock protocol: 766 (v1.21.50).
- Pure standard library Python only (no external pip dependencies).
- Game simulation state (player locations, inventories, active sessions) remains strictly single-threaded on the main loop.
- No statement semicolons or un-expanded compound lines. All code must conform to PEP 8.
- 100% preservation of all comments, wire protocols, and endianness.

---

### Task 1: Background Worker Pool (`pywer.server.worker`)

**Files:**
- Create: `pywer/server/worker.py`
- Test: `tests/test_workers.py`

**Interfaces:**
- Consumes: `concurrent.futures.ThreadPoolExecutor`, `queue.Queue`, `os.cpu_count`
- Produces: `WorkerPool` class with methods:
  - `submit(task_type: str, session_id: int, func, *args)`
  - `drain_results() -> list[tuple[str, int, any]]`
  - `shutdown()`

- [ ] **Step 1: Write the failing unit tests for `WorkerPool`**

```python
# tests/test_workers.py
import unittest
import time
from pywer.server.worker import WorkerPool

def sample_task(x, y):
    return x + y

class TestWorkerPool(unittest.TestCase):
    def test_submit_and_drain_results(self):
        pool = WorkerPool(max_workers=2)
        try:
            pool.submit("ADD", 101, sample_task, 15, 25)
            # Wait up to 1 second for background execution
            results = []
            for _ in range(20):
                time.sleep(0.05)
                results = pool.drain_results()
                if results:
                    break
            self.assertEqual(len(results), 1)
            task_type, session_id, res = results[0]
            self.assertEqual(task_type, "ADD")
            self.assertEqual(session_id, 101)
            self.assertEqual(res, 40)
        finally:
            pool.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_workers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.server.worker'`

- [ ] **Step 3: Implement `pywer.server.worker`**

```python
# pywer/server/worker.py
"""Background thread pool worker pipeline for offloading CPU-heavy tasks."""

import concurrent.futures
import os
import queue
from ..log import dbg


class WorkerPool:
    def __init__(self, max_workers=None):
        workers = max_workers or min(4, max(2, os.cpu_count() or 2))
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="pywer-worker"
        )
        self.results = queue.Queue()
        self.running = True

    def submit(self, task_type, session_id, func, *args):
        """Submit a background job. Upon completion, post result to the thread-safe queue."""
        if not self.running:
            return

        def _runner():
            try:
                res = func(*args)
                if self.running:
                    self.results.put((task_type, session_id, res))
            except Exception as e:
                dbg("Worker", "error executing task %s for session %s: %r" % (task_type, session_id, e))

        self.executor.submit(_runner)

    def drain_results(self):
        """Non-blocking drain of all completed results from the worker queue."""
        items = []
        while True:
            try:
                items.append(self.results.get_nowait())
            except queue.Empty:
                break
        return items

    def shutdown(self):
        """Shut down the executor cleanly."""
        self.running = False
        self.executor.shutdown(wait=False, cancel_futures=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_workers.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 1**

```bash
git add pywer/server/worker.py tests/test_workers.py
git commit -m "feat: add background worker pool for offloading CPU tasks"
```

---

### Task 2: Thread-Safe Chunk Cache (`pywer.world.cache`)

**Files:**
- Create: `pywer/world/cache.py`
- Test: `tests/test_chunk_cache.py`

**Interfaces:**
- Consumes: `threading.Lock`
- Produces: `ChunkCache` class with methods:
  - `get(cx: int, cz: int) -> bytes | None`
  - `put(cx: int, cz: int, payload: bytes)`
  - `invalidate(cx: int, cz: int)`
  - `invalidate_block(x: int, z: int)`
  - `clear()`

- [ ] **Step 1: Write the failing unit tests for `ChunkCache`**

```python
# tests/test_chunk_cache.py
import unittest
from pywer.world.cache import ChunkCache

class TestChunkCache(unittest.TestCase):
    def test_cache_put_get_invalidate(self):
        cache = ChunkCache()
        self.assertIsNone(cache.get(0, 0))
        
        sample_payload = b"\x01\x02\x03\x04"
        cache.put(0, 0, sample_payload)
        self.assertEqual(cache.get(0, 0), sample_payload)
        
        # Test block invalidation: block coordinate (17, 33) is in chunk (1, 2)
        cache.put(1, 2, b"chunk_1_2")
        self.assertEqual(cache.get(1, 2), b"chunk_1_2")
        cache.invalidate_block(17, 33)
        self.assertIsNone(cache.get(1, 2))
        
        # Verify (0, 0) is still intact
        self.assertEqual(cache.get(0, 0), sample_payload)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_chunk_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.world.cache'`

- [ ] **Step 3: Implement `pywer.world.cache`**

```python
# pywer/world/cache.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_chunk_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 2**

```bash
git add pywer/world/cache.py tests/test_chunk_cache.py
git commit -m "feat: add thread-safe chunk payload cache with block invalidation"
```

---

### Task 3: Socket Drain & Monotonic Tick Pacing in `Server`

**Files:**
- Modify: `pywer/server/server.py`
- Test: `tests/test_server_pacing.py`

**Interfaces:**
- Consumes: `time.perf_counter`, `WorkerPool`, `ChunkCache`
- Produces:
  - `Server.worker_pool`
  - `Server.chunk_cache`
  - Non-blocking UDP drain loop
  - Monotonic tick pacer at 20.0 TPS

- [ ] **Step 1: Write unit tests for tick pacer math**

```python
# tests/test_server_pacing.py
import unittest
import time
from pywer.server.server import TICK_INTERVAL, MAX_CATCHUP_TICKS

class TestServerPacing(unittest.TestCase):
    def test_constants(self):
        self.assertAlmostEqual(TICK_INTERVAL, 0.05)
        self.assertEqual(MAX_CATCHUP_TICKS, 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_server_pacing.py -v`
Expected: FAIL with `ImportError: cannot import name 'TICK_INTERVAL' from 'pywer.server.server'`

- [ ] **Step 3: Update `pywer/server/server.py`**
  - Add `TICK_INTERVAL = 0.05` and `MAX_CATCHUP_TICKS = 5`.
  - Instantiate `self.worker_pool = WorkerPool()` and `self.chunk_cache = ChunkCache()` in `Server.__init__`.
  - Update `set_block` and `break_block` to call `self.chunk_cache.invalidate_block(x, z)`.
  - In `Server.tick()`: drain `self.worker_pool.drain_results()` and dispatch completed chunks to active sessions.
  - In `Server.run()`: implement non-blocking socket drain loop and monotonic tick pacer using `time.perf_counter()`.
  - In `Server.stop()`: call `self.worker_pool.shutdown()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_server_pacing.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 3**

```bash
git add pywer/server/server.py tests/test_server_pacing.py
git commit -m "feat: implement non-blocking socket drain and monotonic tick pacer"
```

---

### Task 4: Asynchronous Session Chunk Pipeline

**Files:**
- Modify: `pywer/player/session.py`
- Test: `tests/test_async_chunks.py`

**Interfaces:**
- Consumes: `session.srv.worker_pool`, `session.srv.chunk_cache`, `build_chunk(x, z)`
- Produces:
  - `Session.on_chunk_ready(cx, cz, payload)`
  - Asynchronous submission in `queue_chunks()`
  - Fast dispatch in `stream_chunks()` from pre-generated queue

- [ ] **Step 1: Write unit tests for async chunk pipeline**

```python
# tests/test_async_chunks.py
import unittest
from unittest.mock import MagicMock
from pywer.player.session import Session

class TestAsyncChunkPipeline(unittest.TestCase):
    def test_session_chunk_ready_callback(self):
        srv = MagicMock()
        srv.next_rid = 1
        srv.key = (MagicMock(), MagicMock())
        sess = Session(srv, ("127.0.0.1", 19132), 1400, 12345)
        self.assertEqual(len(sess.chunk_send_queue), 0)
        
        sess.on_chunk_ready(0, 0, b"fake_chunk_data")
        self.assertEqual(len(sess.chunk_send_queue), 1)
        self.assertEqual(sess.chunk_send_queue[0], (0, 0, b"fake_chunk_data"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_async_chunks.py -v`
Expected: FAIL with `AttributeError: 'Session' object has no attribute 'chunk_send_queue'`

- [ ] **Step 3: Update `pywer/player/session.py`**
  - Add `self.chunk_send_queue = []` and `self.chunks_in_flight = set()` in `Session.__init__`.
  - Add `on_chunk_ready(self, cx, cz, payload)`: appends payload to `chunk_send_queue`, removes `(cx, cz)` from `chunks_in_flight`.
  - In `queue_chunks()`:
    - Check `self.srv.chunk_cache.get(cx, cz)`. If hit, enqueue directly to `self.chunk_send_queue`.
    - If miss and not in `self.chunks_in_flight`, add to `self.chunks_in_flight` and submit task `("CHUNK", self.rid, build_chunk, cx, cz)` to `self.srv.worker_pool`.
  - In `stream_chunks()`:
    - Send up to `config.CHUNKS_PER_TICK` from `self.chunk_send_queue`.
    - Zero heavy terrain computation in the tick loop!

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_async_chunks.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 4**

```bash
git add pywer/player/session.py tests/test_async_chunks.py
git commit -m "feat: pipeline chunk streaming asynchronously through worker pool"
```

---

### Task 5: End-to-End Verification & Load Smoke Test

**Files:**
- Test: All tests in `tests/`
- Tool: `tools/smoke_test_load.py`

- [ ] **Step 1: Run complete test suite**

Run: `python -m unittest discover -s tests -v`
Expected: ALL tests PASS (existing 8 tests + new worker, cache, pacing, and async chunk tests).

- [ ] **Step 2: Run server smoke test**

Run: `python pywer.py 19135` for 3 seconds in background, verify startup banner and clean shutdown.

- [ ] **Step 3: Verify tick duration under simulated radius 4 load**

Run a script that requests 81 chunks and records tick times.
Expected: Average tick time remains under 2ms, zero dropped packets.

- [ ] **Step 4: Commit Task 5**

```bash
git add tests/ tools/
git commit -m "test: add end-to-end verification and load smoke test"
```
