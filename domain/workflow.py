# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Domain layer: Workflow (Aggregate Root) + TaskNode.

Workflow is a directed acyclic graph (DAG) of tasks. These rules are enforced
in the domain layer rather than the API, so they apply regardless of entry point:
- Tasks cannot form cycles.
- A dependency cannot reference a missing task.
- A task becomes ready only after all dependencies complete.
- A task that permanently fails after retries cancels every dependent task.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    PENDING = "pending"      # Waiting for dependencies to complete.
    READY = "ready"          # All dependencies completed; ready to run.
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"        # Permanently failed after retries were exhausted.
    CANCELLED = "cancelled"  # Cancelled because one dependency failed.


class CycleDetected(Exception):
    def __init__(self, cycle_hint: str = ""):
        super().__init__(f"A cycle was detected in the task graph. {cycle_hint}")


class InvalidDependency(Exception):
    def __init__(self, task_id: str, missing_dependency: str):
        super().__init__(f"Task '{task_id}' depends on missing task '{missing_dependency}'")


class TaskNotFound(Exception):
    def __init__(self, task_id: str):
        super().__init__(f"No task was found with ID: {task_id}")


class InvalidTaskTransition(Exception):
    def __init__(self, task_id: str, current: TaskState, target: TaskState):
        super().__init__(f"Task '{task_id}' cannot transition from '{current.value}' to '{target.value}'")


_ALLOWED_TASK_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PENDING: {TaskState.READY, TaskState.CANCELLED},
    TaskState.READY: {TaskState.RUNNING, TaskState.CANCELLED},
    TaskState.RUNNING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.PENDING},  # PENDING = retry
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


@dataclass
class TaskNode:
    name: str
    agent_id: str | None = None
    depends_on: frozenset[str] = field(default_factory=frozenset)
    max_retries: int = 0
    payload: dict = field(default_factory=dict)  # Execution-specific data, e.g. {"prompt": "...", "required_capabilities": [...]}.
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: TaskState = TaskState.PENDING
    retry_count: int = 0
    result: Any = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def transition_to(self, target: TaskState) -> None:
        if target not in _ALLOWED_TASK_TRANSITIONS[self.state]:
            raise InvalidTaskTransition(self.task_id, self.state, target)
        self.state = target


@dataclass
class TaskSpec:
    """Task specification supplied when a Workflow is created, before it becomes a complete TaskNode."""

    name: str
    agent_id: str | None = None
    depends_on: list[str] = field(default_factory=list)  # Names of other tasks in the same request.
    max_retries: int = 0
    payload: dict = field(default_factory=dict)


class Workflow:
    """Aggregate root that owns all tasks and enforces their consistency rules."""

    def __init__(self, name: str, tasks: dict[str, TaskNode], workflow_id: str | None = None) -> None:
        self.workflow_id = workflow_id or str(uuid.uuid4())
        self.name = name
        self.tasks = tasks
        self.created_at = datetime.now(timezone.utc)
        self._validate_no_cycles()

    @classmethod
    def create(cls, name: str, specs: list[TaskSpec]) -> "Workflow":
        """Factory that builds tasks from specifications, resolves dependency
        names to real task IDs, and validates the DAG before returning it."""
        name_to_node: dict[str, TaskNode] = {}
        for spec in specs:
            node = TaskNode(name=spec.name, agent_id=spec.agent_id, max_retries=spec.max_retries, payload=spec.payload)
            name_to_node[spec.name] = node

        tasks: dict[str, TaskNode] = {}
        for spec in specs:
            node = name_to_node[spec.name]
            resolved_deps = set()
            for dep_name in spec.depends_on:
                dep_node = name_to_node.get(dep_name)
                if dep_node is None:
                    raise InvalidDependency(node.task_id, dep_name)
                resolved_deps.add(dep_node.task_id)
            node.depends_on = frozenset(resolved_deps)
            tasks[node.task_id] = node

        return cls(name=name, tasks=tasks)

    def _validate_no_cycles(self) -> None:
        """Run Kahn topological sorting; if not all nodes can be ordered, a cycle exists."""
        in_degree = {tid: 0 for tid in self.tasks}
        for node in self.tasks.values():
            for dep in node.depends_on:
                if dep not in self.tasks:
                    raise InvalidDependency(node.task_id, dep)
        dependents: dict[str, list[str]] = {tid: [] for tid in self.tasks}
        for node in self.tasks.values():
            for dep in node.depends_on:
                dependents[dep].append(node.task_id)
                in_degree[node.task_id] += 1

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            current = queue.pop()
            visited += 1
            for nxt in dependents[current]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if visited != len(self.tasks):
            raise CycleDetected(f"{len(self.tasks) - visited} task(s) are part of a cycle")

    def get_task(self, task_id: str) -> TaskNode:
        task = self.tasks.get(task_id)
        if task is None:
            raise TaskNotFound(task_id)
        return task

    def ready_tasks(self) -> list[TaskNode]:
        ready = []
        for node in self.tasks.values():
            if node.state != TaskState.PENDING:
                continue
            deps_done = all(self.tasks[d].state == TaskState.COMPLETED for d in node.depends_on)
            if deps_done:
                ready.append(node)
        return ready

    def mark_ready(self, task_id: str) -> TaskNode:
        node = self.get_task(task_id)
        node.transition_to(TaskState.READY)
        return node

    def start_task(self, task_id: str) -> TaskNode:
        node = self.get_task(task_id)
        node.transition_to(TaskState.RUNNING)
        node.started_at = datetime.now(timezone.utc)
        return node

    def complete_task(self, task_id: str, result: Any = None) -> TaskNode:
        node = self.get_task(task_id)
        node.transition_to(TaskState.COMPLETED)
        node.result = result
        node.completed_at = datetime.now(timezone.utc)
        return node

    def fail_task(self, task_id: str, error: str) -> tuple[TaskNode, list[TaskNode]]:
        """On failure, return the task to PENDING if retries remain. Otherwise,
        mark it permanently failed and cancel direct and indirect dependents.
        Returns the failed task and its cancelled dependent tasks."""
        node = self.get_task(task_id)
        node.error = error
        if node.retry_count < node.max_retries:
            node.retry_count += 1
            node.transition_to(TaskState.PENDING)
            return node, []

        node.transition_to(TaskState.FAILED)
        cancelled = self._cascade_cancel(task_id)
        return node, cancelled

    def _cascade_cancel(self, failed_task_id: str) -> list[TaskNode]:
        cancelled: list[TaskNode] = []
        changed = True
        while changed:
            changed = False
            for node in self.tasks.values():
                if node.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                    continue
                depends_on_failed = any(
                    self.tasks[d].state in (TaskState.FAILED, TaskState.CANCELLED) for d in node.depends_on
                )
                if depends_on_failed:
                    node.transition_to(TaskState.CANCELLED)
                    cancelled.append(node)
                    changed = True
        return cancelled

    def is_complete(self) -> bool:
        return all(t.state == TaskState.COMPLETED for t in self.tasks.values())

    def has_permanent_failure(self) -> bool:
        return any(t.state == TaskState.FAILED for t in self.tasks.values())
