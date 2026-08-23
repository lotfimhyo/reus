"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

TaskScheduler — the task-scheduling half of Layer 2's mandate from the
master architecture doc, section 2.2, and the vision doc's "Cognitive
Engine" step 5 (execution) once a plan has been chosen.

Design decision: a bounded ThreadPoolExecutor of size `max_concurrent_tasks`
is used to cap how many SandboxedExecutor processes may run at once. Each
pool worker thread blocks on one sandboxed subprocess at a time, so the
thread count directly caps the process count — simple and sufficient for
Local Mode, where "distributing work" just means "don't oversubscribe this
one machine".
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

from infrastructure.cognitive_core.resource.exceptions import SchedulerShutDownError
from infrastructure.cognitive_core.resource.monitor import ResourceMonitor
from infrastructure.cognitive_core.resource.sandbox import SandboxedExecutor, SandboxOutcome


class TaskScheduler:
    """Schedules tasks onto a bounded pool of sandboxed worker processes."""

    def __init__(
        self,
        max_concurrent_tasks: int = 4,
        resource_monitor: Optional[ResourceMonitor] = None,
        sandbox: Optional[SandboxedExecutor] = None,
    ):
        if max_concurrent_tasks < 1:
            raise ValueError("max_concurrent_tasks must be >= 1.")
        self.max_concurrent_tasks = max_concurrent_tasks
        self.monitor = resource_monitor or ResourceMonitor()
        self.sandbox = sandbox or SandboxedExecutor()

        self._pool = ThreadPoolExecutor(max_workers=max_concurrent_tasks)
        self._active_count = 0
        self._lock = threading.Lock()
        self._shut_down = False

    def submit(
        self,
        fn: Callable[[dict], dict],
        payload: dict,
        timeout_seconds: float = 30.0,
        memory_limit_mb: Optional[int] = 256,
    ) -> "Future[SandboxOutcome]":
        """Queue a task for sandboxed execution. Returns a Future resolving
        to a SandboxOutcome once the task finishes, times out, or crashes."""
        if self._shut_down:
            raise SchedulerShutDownError("Cannot submit to a shut-down scheduler.")
        return self._pool.submit(
            self._run, fn, payload, timeout_seconds, memory_limit_mb
        )

    def _run(
        self,
        fn: Callable[[dict], dict],
        payload: dict,
        timeout_seconds: float,
        memory_limit_mb: Optional[int],
    ) -> SandboxOutcome:
        with self._lock:
            self._active_count += 1
        try:
            return self.sandbox.run(fn, payload, timeout_seconds, memory_limit_mb)
        finally:
            with self._lock:
                self._active_count -= 1

    @property
    def active_task_count(self) -> int:
        with self._lock:
            return self._active_count

    def shutdown(self, wait: bool = True) -> None:
        self._shut_down = True
        self._pool.shutdown(wait=wait)
