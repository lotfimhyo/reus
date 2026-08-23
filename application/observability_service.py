# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""Passive observability component.

It subscribes to every EventBus event without influencing business logic,
records each event in `EventLogRepository`, and builds summaries on demand from
actual agent and workflow repositories rather than stale cached state.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from domain.event_log import EventLogEntry
from domain.event_log_repository import EventLogRepository
from domain.repositories import AgentRepository
from domain.workflow_repository import WorkflowRepository
from infrastructure.event_bus import Event, EventBus


@dataclass
class ObservabilitySummary:
    agents_total: int
    agents_by_state: dict[str, int]
    workflows_total: int
    workflows_completed: int
    workflows_failed: int
    workflows_in_progress: int
    tasks_total: int
    tasks_by_state: dict[str, int]
    events_by_name: dict[str, int]
    recent_events: list[EventLogEntry] = field(default_factory=list)


class ObservabilityService:
    def __init__(
        self,
        event_log_repo: EventLogRepository,
        agent_repo: AgentRepository,
        workflow_repo: WorkflowRepository,
        event_bus: EventBus,
    ) -> None:
        self._event_log = event_log_repo
        self._agents = agent_repo
        self._workflows = workflow_repo
        self._bus = event_bus

    def start(self) -> None:
        """Begin recording all events once during application startup."""
        self._bus.subscribe("*", self._record_event)

    def _record_event(self, event: Event) -> None:
        self._event_log.add(EventLogEntry(name=event.name, payload=event.payload, timestamp=event.timestamp))

    def get_summary(self, recent_events_limit: int = 20) -> ObservabilitySummary:
        agents = self._agents.list_all()
        agents_by_state: dict[str, int] = {}
        for agent in agents:
            agents_by_state[agent.state.value] = agents_by_state.get(agent.state.value, 0) + 1

        workflows = self._workflows.list_all()
        completed = sum(1 for w in workflows if w.is_complete())
        failed = sum(1 for w in workflows if w.has_permanent_failure())
        in_progress = len(workflows) - completed - failed

        tasks_by_state: dict[str, int] = {}
        tasks_total = 0
        for wf in workflows:
            for task in wf.tasks.values():
                tasks_total += 1
                tasks_by_state[task.state.value] = tasks_by_state.get(task.state.value, 0) + 1

        return ObservabilitySummary(
            agents_total=len(agents),
            agents_by_state=agents_by_state,
            workflows_total=len(workflows),
            workflows_completed=completed,
            workflows_failed=failed,
            workflows_in_progress=in_progress,
            tasks_total=tasks_total,
            tasks_by_state=tasks_by_state,
            events_by_name=self._event_log.count_by_name(),
            recent_events=self._event_log.list_recent(limit=recent_events_limit),
        )

    def get_recent_events(self, limit: int = 100, name_filter: str | None = None) -> list[EventLogEntry]:
        return self._event_log.list_recent(limit=limit, name_filter=name_filter)
