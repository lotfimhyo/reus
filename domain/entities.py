# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Domain layer: Agent entity.

هذا الملف يمثل جوهر النظام (Core Domain) في Clean Architecture.
لا يعتمد على أي طبقة خارجية (لا FastAPI، لا Redis، لا قواعد بيانات).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentState(str, Enum):
    """دورة حياة الوكيل. أي انتقال غير مسموح به يُرفض في طبقة التطبيق."""

    CREATED = "created"
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"


# جدول الانتقالات المسموح بها بين الحالات (State Machine حقيقية، ليست تجميلية)
ALLOWED_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.CREATED: {AgentState.IDLE, AgentState.ERROR, AgentState.TERMINATED},
    AgentState.IDLE: {AgentState.RUNNING, AgentState.PAUSED, AgentState.TERMINATED, AgentState.ERROR},
    AgentState.RUNNING: {AgentState.IDLE, AgentState.PAUSED, AgentState.ERROR, AgentState.TERMINATED},
    AgentState.PAUSED: {AgentState.RUNNING, AgentState.IDLE, AgentState.TERMINATED, AgentState.ERROR},
    AgentState.ERROR: {AgentState.IDLE, AgentState.TERMINATED},
    AgentState.TERMINATED: set(),  # حالة نهائية، لا رجوع منها
}


class InvalidStateTransition(Exception):
    def __init__(self, current: AgentState, target: AgentState):
        super().__init__(f"لا يمكن الانتقال من الحالة '{current.value}' إلى '{target.value}'")
        self.current = current
        self.target = target


class PermissionDenied(Exception):
    def __init__(self, permission: str):
        super().__init__(f"الصلاحية '{permission}' غير مسموح بها ضمن قائمة الصلاحيات المعتمدة")
        self.permission = permission


# مبدأ أقل الصلاحيات: لا صلاحية تُقبل إن لم تكن ضمن هذه القائمة المغلقة
ALLOWED_PERMISSIONS: frozenset[str] = frozenset({
    "read:memory",
    "write:memory",
    "invoke:model",
    "invoke:tool",
    "read:metrics",
    "network:outbound",
    "spawn:subagent",
})


@dataclass
class OperationRecord:
    """سطر واحد في سجل عمليات الوكيل (Audit Log)."""

    timestamp: datetime
    action: str
    result: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceMetrics:
    """مؤشرات أداء تراكمية للوكيل."""

    requests_count: int = 0
    total_latency_ms: float = 0.0
    errors_count: int = 0
    last_cpu_percent: float | None = None
    last_rss_bytes: int | None = None

    @property
    def avg_latency_ms(self) -> float:
        if self.requests_count == 0:
            return 0.0
        return self.total_latency_ms / self.requests_count


@dataclass
class Agent:
    """
    كيان الوكيل: هوية + صلاحيات + ذاكرة (مراجع) + أهداف + حالة + سجل + مؤشرات أداء.
    """

    name: str
    permissions: set[str]
    goals: list[str]
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: AgentState = AgentState.CREATED
    memory_refs: list[str] = field(default_factory=list)  # معرفات مقاطع الذاكرة في مخزن الذاكرة الدلالية
    operation_log: list[OperationRecord] = field(default_factory=list)
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        invalid = self.permissions - ALLOWED_PERMISSIONS
        if invalid:
            raise PermissionDenied(next(iter(invalid)))

    def transition_to(self, target: AgentState) -> None:
        if target not in ALLOWED_TRANSITIONS[self.state]:
            raise InvalidStateTransition(self.state, target)
        self.record_operation(action="state_transition", result=f"{self.state.value}->{target.value}")
        self.state = target

    def record_operation(self, action: str, result: str, **metadata: Any) -> None:
        self.operation_log.append(
            OperationRecord(timestamp=datetime.now(timezone.utc), action=action, result=result, metadata=metadata)
        )

    def record_request(self, latency_ms: float, success: bool) -> None:
        self.metrics.requests_count += 1
        self.metrics.total_latency_ms += latency_ms
        if not success:
            self.metrics.errors_count += 1
