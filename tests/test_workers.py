"""Unit tests for background worker pool."""

import time
import unittest

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


if __name__ == "__main__":
    unittest.main()
