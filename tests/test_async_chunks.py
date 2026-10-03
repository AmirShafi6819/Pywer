"""Unit tests for asynchronous session chunk pipeline."""

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


if __name__ == "__main__":
    unittest.main()
