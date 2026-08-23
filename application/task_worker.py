# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""Execute every `task.ready` event through a real `TaskExecutor`, then mark
the task complete or failed through `OrchestratorService`, which may trigger a
retry or cascading cancellation just as an API call would.

Processing uses a queue and worker threads rather than executing directly in an
event callback. This matters because `InMemoryEventBus` is synchronous: direct
execution could publish the next DAG `task.ready` event from inside the current
callback and create a re-entrant call stack proportional to workflow depth. A
queue keeps every callback shallow and safe for both in-memory and Redis buses.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Optional, Protocol

from application.orchestrator_service import OrchestratorService
from application.task_executor import TaskExecutionError, TaskExecutor
from domain.repositories import AgentNotFound
from domain.workflow import TaskNotFound
from domain.workflow_repository import WorkflowNotFound
from infrastructure.event_bus import Event, EventBus

logger = logging.getLogger("reus_veritas.worker")


class TaskLeaseCoordinator(Protocol):
    def acquire(self, task_id: str, *, lease_seconds: float = 30.0) -> bool: ...
    def complete(self, task_id: str) -> bool: ...


class TaskWorker:
    def __init__(
        self,
        orchestrator: OrchestratorService,
        executor: TaskExecutor,
        event_bus: EventBus,
        pool_size: int = 4,
        lease_coordinator: Optional[TaskLeaseCoordinator] = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._executor = executor
        self._bus = event_bus
        self._pool_size = pool_size
        self._lease_coordinator = lease_coordinator
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._bus.subscribe("task.ready", self._enqueue)
        for i in range(self._pool_size):
            thread = threading.Thread(target=self._run_loop, name=f"task-worker-{i}", daemon=True)
            thread.start()
            self._threads.append(thread)
        logger.info("task_worker_started", extra={"event_name": "task_worker_started", "payload": {"pool_size": self._pool_size}})

    def stop(self, timeout: float = 2.0) -> None:
        self._running = False
        for thread in self._threads:
            thread.join(timeout=timeout)
        self._threads.clear()

    def _enqueue(self, event: Event) -> None:
        workflow_id = event.payload.get("workflow_id")
        task_id = event.payload.get("task_id")
        if workflow_id and task_id:
            self._queue.put((workflow_id, task_id))

    def _run_loop(self) -> None:
        while self._running:
            try:
                workflow_id, task_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._process(workflow_id, task_id)
            except Exception:  # noqa: BLE001 - unexpected errors must not kill a worker thread
                logger.exception("task_worker_unexpected_error")
            finally:
                self._queue.task_done()

    def _process(self, workflow_id: str, task_id: str) -> None:
        try:
            task = self._orchestrator.start_task(workflow_id, task_id)
        except (WorkflowNotFound, TaskNotFound):
            logger.warning("task_worker_stale_event", extra={"event_name": "task_worker_stale_event"})
            return

        cluster_task_id = f"{workflow_id}:{task_id}"
        if self._lease_coordinator and not self._lease_coordinator.acquire(cluster_task_id):
            self._orchestrator.fail_task(workflow_id, task_id, error="Cluster task lease was not committed.")
            return

        try:
            result = self._executor.execute(task)
        except (TaskExecutionError, AgentNotFound) as exc:
            self._orchestrator.fail_task(workflow_id, task_id, error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - record other execution errors as ordinary task failures
            self._orchestrator.fail_task(workflow_id, task_id, error=f"{type(exc).__name__}: {exc}")
            return

        if self._lease_coordinator and not self._lease_coordinator.complete(cluster_task_id):
            self._orchestrator.fail_task(workflow_id, task_id, error="Task result withheld: cluster completion was not committed.")
            return
        self._orchestrator.complete_task(workflow_id, task_id, result=result)
