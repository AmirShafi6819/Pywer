"""Unit tests for ServerScheduler, ScheduledTask, and async task execution."""

import threading
import time
import unittest

from pywer.scheduler import ScheduledTask, ServerScheduler


class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.scheduler = ServerScheduler(server=None, max_async_workers=2)

    def tearDown(self):
        self.scheduler.shutdown()

    def test_run_later(self):
        calls = []

        def task():
            calls.append("executed")

        self.scheduler.run_later(2, task)

        # Tick 1: should not run yet
        self.scheduler.tick()
        self.assertEqual(calls, [])

        # Tick 2: should run
        self.scheduler.tick()
        self.assertEqual(calls, ["executed"])

        # Tick 3: one-shot, should not run again
        self.scheduler.tick()
        self.assertEqual(calls, ["executed"])

    def test_run_repeating(self):
        runs = []

        def task():
            runs.append(self.scheduler.current_tick)

        # delay 1, period 2
        self.scheduler.run_repeating(1, 2, task)

        self.scheduler.tick()  # tick 1 -> runs
        self.assertEqual(runs, [1])

        self.scheduler.tick()  # tick 2 -> idle
        self.assertEqual(runs, [1])

        self.scheduler.tick()  # tick 3 -> runs
        self.assertEqual(runs, [1, 3])

        self.scheduler.tick()  # tick 4 -> idle
        self.assertEqual(runs, [1, 3])

        self.scheduler.tick()  # tick 5 -> runs
        self.assertEqual(runs, [1, 3, 5])

    def test_task_cancellation(self):
        calls = []

        def task():
            calls.append("called")

        task_handle = self.scheduler.run_later(3, task)
        self.scheduler.tick()  # tick 1
        task_handle.cancel()
        self.assertTrue(task_handle.is_cancelled)

        self.scheduler.tick()  # tick 2
        self.scheduler.tick()  # tick 3
        self.assertEqual(calls, [])

    def test_cancel_by_plugin(self):
        calls_a = []
        calls_b = []
        plugin_a = object()
        plugin_b = object()

        self.scheduler.run_repeating(1, 1, lambda: calls_a.append(1), plugin=plugin_a)
        self.scheduler.run_repeating(1, 1, lambda: calls_b.append(1), plugin=plugin_b)

        self.scheduler.tick()  # tick 1 -> both run
        self.assertEqual(len(calls_a), 1)
        self.assertEqual(len(calls_b), 1)

        # Cancel plugin_a
        cancelled = self.scheduler.cancel_by_plugin(plugin_a)
        self.assertEqual(cancelled, 1)

        self.scheduler.tick()  # tick 2 -> only b runs
        self.assertEqual(len(calls_a), 1)
        self.assertEqual(len(calls_b), 2)

    def test_async_task_and_main_thread_callback(self):
        main_thread_id = threading.get_ident()
        callback_thread_ids = []
        callback_results = []

        def background_worker():
            # Runs off-main thread
            time.sleep(0.02)
            return {"status": "ok", "value": 999}

        def on_complete(result):
            callback_thread_ids.append(threading.get_ident())
            callback_results.append(result)

        self.scheduler.run_async(background_worker, on_complete=on_complete)

        # Before background finishes, tick should not execute callback
        self.scheduler.tick()
        self.assertEqual(callback_results, [])

        # Wait for worker thread to complete
        time.sleep(0.06)

        # Drain on main thread during tick
        self.scheduler.tick()
        self.assertEqual(len(callback_results), 1)
        self.assertEqual(callback_results[0], {"status": "ok", "value": 999})
        # Verify callback was executed on the caller's (main) thread
        self.assertEqual(callback_thread_ids[0], main_thread_id)

    def test_fault_isolation(self):
        order = []

        def failing_task():
            order.append("fail")
            raise RuntimeError("Task blew up")

        def normal_task():
            order.append("success")

        self.scheduler.run_later(1, failing_task)
        self.scheduler.run_later(1, normal_task)

        # Ticking should not crash the scheduler
        self.scheduler.tick()
        self.assertEqual(order, ["fail", "success"])


if __name__ == "__main__":
    unittest.main()
