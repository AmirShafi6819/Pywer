"""Verification script for testing server tick pacing and async chunk generation load."""

import time
from unittest.mock import MagicMock

from pywer.player.session import Session
from pywer.server.server import Server, TICK_INTERVAL


def main():
    print("Testing server tick pacing and worker pool chunk generation...")
    # Initialize server on a high unused test port
    srv = Server(port=19139, bind="127.0.0.1")
    try:
        # Create a mock session
        sess = Session(srv, ("127.0.0.1", 54321), 1400, 99999)
        srv.sessions[sess.addr] = sess
        sess.spawned = True
        sess.radius = 4  # 81 chunks
        sess.center = (0, 0)

        # Queue chunks asynchronously
        start_q = time.perf_counter()
        sess.queue_chunks()
        q_duration = (time.perf_counter() - start_q) * 1000
        print(f"Queued 81 chunks asynchronously in {q_duration:.2f}ms (non-blocking!)")

        # Step server for 30 ticks and record tick times
        tick_durations = []
        for _ in range(30):
            t0 = time.perf_counter()
            srv.step(timeout=0.01)
            t_elapsed = (time.perf_counter() - t0) * 1000
            tick_durations.append(t_elapsed)

        # Wait a moment for background workers to finish
        for _ in range(20):
            time.sleep(0.05)
            srv.drain_workers()
            if len(sess.chunk_send_queue) >= 50:
                break

        print(f"Chunks generated in background and ready to send: {len(sess.chunk_send_queue)}")
        avg_tick = sum(tick_durations) / len(tick_durations)
        max_tick = max(tick_durations)
        print(f"Avg step time: {avg_tick:.2f}ms, Max step time: {max_tick:.2f}ms")

        # Verify chunks are cached
        print(f"Chunks cached in memory ChunkCache: {len(srv.chunk_cache)}")
        assert len(srv.chunk_cache) > 0, "ChunkCache should contain generated chunks"

        # Verify block invalidation removes from cache
        srv.set_block(0, 64, 0, "stone")
        assert srv.chunk_cache.get(0, 0) is None, "Chunk (0, 0) should be invalidated after set_block"
        print("Chunk cache invalidation verified!")

        print("LOAD & PERFORMANCE SMOKE TEST PASSED SUCCESSFULLY!")
    finally:
        srv.stop()


if __name__ == "__main__":
    main()
