# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Domain layer: Workflow (Aggregate Root) + TaskNode.

Workflow يمثل DAG (Directed Acyclic Graph) من المهام. القواعد التالية
تُفرض هنا في الدومين (لا في API) حتى تُطبَّق دائمًا بغض النظر عن نقطة الدخول:
- لا يجوز وجود حلقات (Cycles) بين المهام.
- لا يجوز الإشارة إلى مهمة غير موجودة كتبعية.
- لا تصبح أي مهمة "جاهزة" إلا بعد اكتمال كل تبعياتها.
- فشل مهمة بعد استنفاد إعادة المحاولات يُلغي كل المهام التي تعتمد عليها (Cascading Cancellation).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    PENDING = "pending"      # بانتظار اكتمال التبعيات
    READY = "ready"          # كل التبعيات اكتملت، جاهزة للتنفيذ
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"        # فشلت نهائيًا بعد استنفاد إعادة المحاولات
    CANCELLED = "cancelled"  # أُلغيت بسبب فشل تبعية لها


class CycleDetected(Exception):
    def __init__(self, cycle_hint: str = ""):
        super().__init__(f"تم اكتشاف حلقة (Cycle) في شبكة المهام. {cycle_hint}")


class InvalidDependency(Exception):
    def __init__(self, task_id: str, missing_dependency: str):
        super().__init__(f"المهمة '{task_id}' تعتمد على مهمة غير موجودة: '{missing_dependency}'")


class TaskNotFound(Exception):
    def __init__(self, task_id: str):
        super().__init__(f"لم يتم العثور على مهمة بالمعرّف: {task_id}")


class InvalidTaskTransition(Exception):
    def __init__(self, task_id: str, current: TaskState, target: TaskState):
        super().__init__(f"المهمة '{task_id}': لا يمكن الانتقال من '{current.value}' إلى '{target.value}'")


_ALLOWED_TASK_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PENDING: {TaskState.READY, TaskState.CANCELLED},
    TaskState.READY: {TaskState.RUNNING, TaskState.CANCELLED},
    TaskState.RUNNING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.PENDING},  # PENDING = إعادة محاولة
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
    payload: dict = field(default_factory=dict)  # بيانات خاصة بالتنفيذ، مثل: {"prompt": "...", "required_capabilities": [...]}
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
    """مواصفة مهمة يقدّمها المستخدم عند إنشاء Workflow (قبل أن تصبح TaskNode كاملة)."""

    name: str
    agent_id: str | None = None
    depends_on: list[str] = field(default_factory=list)  # أسماء مهام أخرى ضمن نفس الطلب
    max_retries: int = 0
    payload: dict = field(default_factory=dict)


class Workflow:
    """Aggregate Root: يملك كل مهامه ويفرض قواعد الاتساق عليها بالكامل."""

    def __init__(self, name: str, tasks: dict[str, TaskNode], workflow_id: str | None = None) -> None:
        self.workflow_id = workflow_id or str(uuid.uuid4())
        self.name = name
        self.tasks = tasks
        self.created_at = datetime.now(timezone.utc)
        self._validate_no_cycles()

    @classmethod
    def create(cls, name: str, specs: list[TaskSpec]) -> "Workflow":
        """
        Factory: يبني المهام من المواصفات، ويحوّل أسماء التبعيات إلى task_id فعلية،
        ويتحقق من سلامة الـ DAG قبل إرجاع الكائن.
        """
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
        """فرز طوبولوجي بخوارزمية Kahn؛ إن تعذّر ترتيب كل العقد فهناك حلقة."""
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
            raise CycleDetected(f"{len(self.tasks) - visited} مهمة/مهام ضمن حلقة")

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
        """
        عند الفشل: إن بقيت محاولات، تُعاد المهمة إلى PENDING (إصلاح ذاتي عبر إعادة المحاولة).
        وإلا تُوسم بالفشل النهائي، وتُلغى تلقائيًا كل المهام التي تعتمد عليها (مباشرة وغير مباشرة).
        يُعيد (المهمة الفاشلة، قائمة المهام المُلغاة تبعًا لها).
        """
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
