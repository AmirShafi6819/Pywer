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
            thread_name_prefix="pywer-worker",
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
                dbg(
                    "Worker",
                    "error executing task %s for session %s: %r"
                    % (task_type, session_id, e),
                )

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
