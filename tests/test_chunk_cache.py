"""Unit tests for thread-safe chunk cache."""

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
        self.assertEqual(len(cache), 1)

        # Clear
        cache.clear()
        self.assertEqual(len(cache), 0)

    def test_invalidate_block_floors_negative_coordinates(self):
        # int(-0.5) == 0 truncates towards zero, which would evict chunk 0 instead of
        # the chunk the block actually lives in (-1).
        cache = ChunkCache()
        cache.put(-1, -1, b"neg")
        cache.put(0, 0, b"zero")

        cache.invalidate_block(-0.5, -0.5)

        self.assertIsNone(cache.get(-1, -1))
        self.assertEqual(cache.get(0, 0), b"zero")

    def test_invalidate_block_accepts_integer_coordinates(self):
        cache = ChunkCache()
        cache.put(-1, 2, b"neg")
        cache.invalidate_block(-16, 33)
        self.assertIsNone(cache.get(-1, 2))
        cache.put(-1, 2, b"neg")
        cache.invalidate_block(-1, 33)
        self.assertIsNone(cache.get(-1, 2))


if __name__ == "__main__":
    unittest.main()
