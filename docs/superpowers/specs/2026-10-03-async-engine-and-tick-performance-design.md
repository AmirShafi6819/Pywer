# Architectural Design: Async Engine & Tick Performance Optimization

## 1. Overview & Goals

Pywer is a pure-Python Minecraft Bedrock Edition server (targeting protocol 766 / v1.21.50). In the current implementation, all UDP networking, RakNet protocol timeouts, chunk/terrain generation, zlib compression, and game state ticking run inside a single synchronous `while True` loop in `pywer.server.server.Server`.

### Key Problems Addressed
1. **Synchronous Chunk Generation Stalls:** Generating and encoding terrain chunks (e.g. 81 chunks for radius 4) in the main thread takes hundreds of milliseconds, blocking RakNet timers, dropping client ACKs, and inducing rubberbanding or connection drops.
2. **Socket Buffer Starvation:** `select.select()` reads only one UDP datagram per iteration, leaving bursts of client packets buffered in kernel memory.
3. **Coarse & Drifting Tick Timing:** Using `select.select(..., 0.05)` with `time.time()` causes systematic timing drift and unstable 20.0 TPS (ticks per second).
4. **Redundant Terrain Generation:** Identical chunks are recalculated from scratch for each nearby player without memory caching.

### Goals
- Maintain a rock-solid **20.0 TPS** tick rate (50ms ± 2ms) under concurrent player logins and terrain generation.
- Decouple pure CPU work (terrain noise calculations, chunk binary serialization) to a background thread pool without introducing race conditions into the game state.
- Implement non-blocking socket drainage to process all buffered UDP datagrams immediately.
- Provide a thread-safe chunk cache with invalidation when world blocks are placed or broken.
- Ensure 100% backward compatibility with existing Bedrock packet structures and RakNet transport logic.

---

## 2. Architecture & Concurrency Model

Pywer will use an **Asynchronous Worker Pipeline with Single-Threaded Game State Determinism**:

```mermaid
flowchart TD
    subgraph MainThread [Main Game Loop Thread]
        SocketDrain["Non-blocking Socket Drain<br/>(Reads all pending UDP datagrams)"]
        PacketDispatch["Packet Codecs & Handlers<br/>(RakNet, AuthInput, Transactions)"]
        TickPacer["High-Precision Tick Pacer<br/>(time.perf_counter, 20.0 TPS)"]
        DrainWorkerQueue["Drain Worker Completion Queue<br/>(Queue of finished chunks)"]
        SendPacketQueue["Dispatch Chunks to Player<br/>(Pre-encoded binary packets)"]
    end

    subgraph BackgroundThreadPool [Background Thread Pool (ThreadPoolExecutor)]
        ChunkWorker1["Worker 1: generate_chunk() + build_chunk()"]
        ChunkWorker2["Worker 2: generate_chunk() + build_chunk()"]
    end

    subgraph MemoryCache [Thread-Safe Chunk Cache]
        CacheDict["(cx, cz) -> bytes"]
    end

    SocketDrain --> PacketDispatch
    PacketDispatch -->|Player enters new area| RequestChunk["Session.queue_chunks()"]
    RequestChunk -->|Cache Miss| BackgroundThreadPool
    RequestChunk -->|Cache Hit| SendPacketQueue
    BackgroundThreadPool --> CacheDict
    BackgroundThreadPool -->|Post Result| DrainWorkerQueue
    TickPacer --> DrainWorkerQueue
    DrainWorkerQueue --> SendPacketQueue
```

### Determinism Rule
All mutable game state (player position, inventory lists, active sessions, block state dictionaries) remains strictly modified **only** by the main loop thread. Background workers operate solely on immutable coordinate tuples and return serialized chunk bytes.

---

## 3. Subsystem Specifications

### 3.1 Non-Blocking UDP Socket Drain

In [`pywer/server/server.py`](file:///c:/Users/Mani/Desktop/Pywer/pywer/server/server.py), replace the single-packet read with a complete drainage loop:

```python
r, _, _ = select.select([self.sock], [], [], timeout)
if r:
    while True:
        try:
            data, addr = self.sock.recvfrom(65535)
            self.on_datagram(data, addr)
        except (BlockingIOError, socket.error):
            break
```

- When the socket becomes readable, all pending datagrams in the OS buffer are consumed in one pass.
- Eliminates latency spikes caused by multiple simultaneous client packets.

### 3.2 High-Precision Tick Engine

Replace coarse tick timing with monotonic drift-compensating pacing:
- Constants: `TICK_INTERVAL = 0.05` (50ms = 20 TPS), `MAX_CATCHUP_TICKS = 5`.
- Maintain `next_tick = time.perf_counter() + TICK_INTERVAL`.
- Sleep interval passed to `select`:
  $$\text{timeout} = \max(0.0, \min(\text{TICK_INTERVAL}, \text{next\_tick} - \text{time.perf\_counter}()))$$
- If the server experiences a heavy OS stall where `time.perf_counter() - next_tick > MAX_CATCHUP_TICKS * TICK_INTERVAL`, clamp `next_tick` forward to avoid runaway catch-up ticking.

### 3.3 Background Worker Pool (`WorkerPool`)

Create a dedicated concurrency manager in `pywer/server/worker.py`:
- Backed by `concurrent.futures.ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2))`.
- Pure worker function: `generate_and_encode_chunk(cx, cz) -> tuple[int, int, bytes]`.
  - Computes terrain blocks using `generate_chunk(cx, cz)`.
  - Serializes chunk sections into Bedrock wire format using `build_chunk(cx, cz)`.
- Communication back to main thread: `queue.Queue` of `(session_id, cx, cz, payload)`.

### 3.4 In-Memory Chunk Cache (`ChunkCache`)

Integrated in `pywer/world/terrain.py` or `pywer/server/server.py`:
- Key: `(cx: int, cz: int)`, Value: `bytes` (pre-built network chunk packet body).
- Thread-safe access via Python's GIL / `threading.Lock`.
- Invalidation hook:
  - When `set_block(x, y, z, key)` or `break_block(...)` modifies a block at `(x, y, z)`, the chunk coordinate `(x >> 4, z >> 4)` is invalidated and evicted from the cache.

### 3.5 Session Chunk Pipeline

In [`pywer/player/session.py`](file:///c:/Users/Mani/Desktop/Pywer/pywer/player/session.py):
- `chunk_queue`: Stores coordinates `(cx, cz)` waiting to be requested or dispatched.
- `chunk_send_queue`: Stores ready-to-send payloads `bytes`.
- In `queue_chunks()`:
  - Check `chunk_cache`. If present, immediately add to `chunk_send_queue`.
  - If not cached, submit generation task to `server.worker_pool`.
- In `stream_chunks()`:
  - Send up to `config.CHUNKS_PER_TICK` (default 4) packets directly from `chunk_send_queue`.
  - If a player disconnects, pending results for that session ID are cleanly ignored when drained.

---

## 4. Error Handling & Edge Cases

1. **Player Disconnection during Async Generation:**
   - If a player logs off while 81 chunks are computing in background threads, the worker completes the chunk and inserts it into `chunk_cache` (so the terrain work is not wasted for future players), while the session packet dispatch is discarded.
2. **Worker Exception Safety:**
   - Any unhandled exception in worker threads is captured by the worker callback and logged to `log.dbg` without crashing the main server loop.
3. **Server Shutdown:**
   - On shutdown, `worker_pool.shutdown(wait=False, cancel_futures=True)` halts worker execution cleanly.

---

## 5. Verification & Testing Plan

1. **Unit Tests:**
   - `tests/test_workers.py`: Verify `WorkerPool` task submission, execution, and thread-safe queue dispatch.
   - `tests/test_chunk_cache.py`: Verify cache hit, miss, and eviction upon block modification.
   - `tests/test_tick_pacing.py`: Verify monotonic timer math and timeout bounds.
2. **Regression Tests:**
   - Verify all 8 existing unit tests continue to pass (`tests/test_serializers.py`, `tests/test_crypto.py`, `tests/test_imports.py`).
3. **Performance Smoke Test:**
   - Run server on test port `19134`.
   - Request full radius-4 chunk generation.
   - Verify tick duration remains $\le 50\text{ms}$ with zero dropped UDP frames.
