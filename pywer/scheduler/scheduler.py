"""Server scheduler implementation for tick-based and asynchronous background tasks."""

import concurrent.futures
import queue
import traceback
from typing import Any, Callable, Dict, List, Optional


class ScheduledTask:
    """Represents a scheduled unit of work."""

    def __init__(
        self,
        task_id: int,
        run_fn: Callable,
        delay_ticks: int = 0,
        period_ticks: int = 0,
        is_repeating: bool = False,
        is_async: bool = False,
        plugin: Any = None,
        next_run_tick: int = 0,
    ) -> None:
        self.task_id = task_id
        self.run_fn = run_fn
        self.delay_ticks = delay_ticks
        self.period_ticks = period_ticks
        self.is_repeating = is_repeating
        self.is_async = is_async
        self.plugin = plugin
        self.next_run_tick = next_run_tick
        self._is_cancelled: bool = False

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def cancel(self) -> None:
        """Cancels this task so it will not execute again."""
        self._is_cancelled = True


class ServerScheduler:
    """Tick-aligned server scheduler with main-thread safety and threadpool execution."""

    def __init__(self, server: Any = None, max_async_workers: int = 4) -> None:
        self.server = server
        self.current_tick: int = 0
        self._next_task_id: int = 1
        self._tasks: Dict[int, ScheduledTask] = {}
        self._async_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_async_workers,
            thread_name_prefix="PywerSchedulerAsync",
        )
        self._async_results_queue: queue.Queue = queue.Queue()

    def run_later(
        self, delay_ticks: int, task: Callable[[], None], plugin: Any = None
    ) -> ScheduledTask:
        """Schedules a synchronous task to run after delay_ticks ticks."""
        tid = self._next_task_id
        self._next_task_id += 1
        delay = max(0, int(delay_ticks))
        task_obj = ScheduledTask(
            task_id=tid,
            run_fn=task,
            delay_ticks=delay,
            period_ticks=0,
            is_repeating=False,
            is_async=False,
            plugin=plugin,
            next_run_tick=self.current_tick + delay,
        )
        self._tasks[tid] = task_obj
        return task_obj

    def run_repeating(
        self,
        delay_ticks: int,
        period_ticks: int,
        task: Callable[[], None],
        plugin: Any = None,
    ) -> ScheduledTask:
        """Schedules a synchronous task to run repeatedly every period_ticks ticks after delay_ticks."""
        tid = self._next_task_id
        self._next_task_id += 1
        delay = max(0, int(delay_ticks))
        period = max(1, int(period_ticks))
        task_obj = ScheduledTask(
            task_id=tid,
            run_fn=task,
            delay_ticks=delay,
            period_ticks=period,
            is_repeating=True,
            is_async=False,
            plugin=plugin,
            next_run_tick=self.current_tick + delay,
        )
        self._tasks[tid] = task_obj
        return task_obj

    def run_async(
        self,
        worker_fn: Callable[[], Any],
        on_complete: Optional[Callable[[Any], None]] = None,
        plugin: Any = None,
    ) -> ScheduledTask:
        """Executes a worker in a background thread and posts the result back to the main thread during tick()."""
        tid = self._next_task_id
        self._next_task_id += 1
        task_obj = ScheduledTask(
            task_id=tid,
            run_fn=worker_fn,
            delay_ticks=0,
            period_ticks=0,
            is_repeating=False,
            is_async=True,
            plugin=plugin,
        )
        self._tasks[tid] = task_obj

        def _worker_wrapper():
            result = None
            exc = None
            try:
                result = worker_fn()
            except Exception as e:
                exc = e
            self._async_results_queue.put((task_obj, result, exc, on_complete))

        self._async_pool.submit(_worker_wrapper)
        return task_obj

    def cancel_task(self, task_id: int) -> bool:
        """Cancels a specific scheduled task by ID."""
        task = self._tasks.get(task_id)
        if task:
            task.cancel()
            self._tasks.pop(task_id, None)
            return True
        return False

    def cancel_by_plugin(self, plugin: Any) -> int:
        """Cancels all scheduled tasks associated with a given plugin."""
        cancelled = 0
        for tid, task in list(self._tasks.items()):
            if task.plugin is plugin:
                task.cancel()
                self._tasks.pop(tid, None)
                cancelled += 1
        return cancelled

    def tick(self) -> None:
        """Advances scheduler by one tick, draining completed async results and running due synchronous tasks."""
        self.current_tick += 1

        # 1. Drain async completions onto the main server thread
        while not self._async_results_queue.empty():
            try:
                task_obj, result, exc, on_complete = self._async_results_queue.get_nowait()
            except queue.Empty:
                break

            self._tasks.pop(task_obj.task_id, None)
            if task_obj.is_cancelled or on_complete is None:
                continue

            try:
                if exc is not None:
                    self._log_task_error(task_obj, exc)
                else:
                    on_complete(result)
            except Exception as e:
                self._log_task_error(task_obj, e)

        # 2. Run due synchronous tasks
        due_tasks: List[ScheduledTask] = []
        for tid, task in list(self._tasks.items()):
            if task.is_cancelled:
                self._tasks.pop(tid, None)
                continue
            if not task.is_async and task.next_run_tick <= self.current_tick:
                due_tasks.append(task)

        for task in due_tasks:
            if task.is_cancelled:
                self._tasks.pop(task.task_id, None)
                continue

            try:
                task.run_fn()
            except Exception as e:
                self._log_task_error(task, e)

            if task.is_repeating and not task.is_cancelled:
                task.next_run_tick = self.current_tick + task.period_ticks
            else:
                self._tasks.pop(task.task_id, None)

    def _log_task_error(self, task: ScheduledTask, exc: Exception) -> None:
        plugin_name = getattr(task.plugin, "name", None) or "Core"
        print(f"[ERROR] [Scheduler] Task #{task.task_id} (Plugin: {plugin_name}) failed: {exc!r}")

    def shutdown(self) -> None:
        """Cancels all pending tasks and terminates threadpool executor."""
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()
        self._async_pool.shutdown(wait=False)
