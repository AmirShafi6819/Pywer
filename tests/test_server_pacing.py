"""Unit tests for server tick pacing and socket drain logic."""

import unittest
from pywer.server.server import TICK_INTERVAL, MAX_CATCHUP_TICKS


class TestServerPacing(unittest.TestCase):
    def test_constants(self):
        self.assertAlmostEqual(TICK_INTERVAL, 0.05)
        self.assertEqual(MAX_CATCHUP_TICKS, 5)


if __name__ == "__main__":
    unittest.main()
