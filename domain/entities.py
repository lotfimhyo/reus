# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Domain layer: Agent entity.

This file is the core domain in Clean Architecture. It depends on no external
layer: no FastAPI, Redis, or database.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentState(str, Enum):
    """Agent lifecycle. The application layer rejects every forbidden transition."""

    CREATED = "created"
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"


# Allowed state-transition table. This is a real state machine, not decoration.
ALLOWED_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.CREATED: {AgentState.IDLE, AgentState.ERROR, AgentState.TERMINATED},
    AgentState.IDLE: {AgentState.RUNNING, AgentState.PAUSED, AgentState.TERMINATED, AgentState.ERROR},
    AgentState.RUNNING: {AgentState.IDLE, AgentState.PAUSED, AgentState.ERROR, AgentState.TERMINATED},
    AgentState.PAUSED: {AgentState.RUNNING, AgentState.IDLE, AgentState.TERMINATED, AgentState.ERROR},
    AgentState.ERROR: {AgentState.IDLE, AgentState.TERMINATED},
    AgentState.TERMINATED: set(),  # Terminal state; no return transition.
}


class InvalidStateTransition(Exception):
    def __init__(self, current: AgentState, target: AgentState):
        super().__init__(f"Cannot transition from state '{current.value}' to '{target.value}'")
        self.current = current
        self.target = target


class PermissionDenied(Exception):
    def __init__(self, permission: str):
        super().__init__(f"Permission '{permission}' is not allowed by the approved permission set")
        self.permission = permission


# Least privilege: no permission is accepted unless it belongs to this closed set.
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
    """One entry in the agent operation audit log."""

    timestamp: datetime
    action: str
    result: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceMetrics:
    """Cumulative agent performance metrics."""

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
    """Agent entity: identity, permissions, memory references, goals, state,
    operation log, and performance metrics."""

    name: str
    permissions: set[str]
    goals: list[str]
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: AgentState = AgentState.CREATED
    memory_refs: list[str] = field(default_factory=list)  # Semantic-memory record identifiers.
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
