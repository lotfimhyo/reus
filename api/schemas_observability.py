# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from application.observability_service import ObservabilitySummary
from domain.event_log import EventLogEntry


class EventLogEntryResponse(BaseModel):
    entry_id: str
    name: str
    payload: dict
    timestamp: datetime

    @classmethod
    def from_domain(cls, entry: EventLogEntry) -> "EventLogEntryResponse":
        return cls(entry_id=entry.entry_id, name=entry.name, payload=entry.payload, timestamp=entry.timestamp)


class ObservabilitySummaryResponse(BaseModel):
    agents_total: int
    agents_by_state: dict[str, int]
    workflows_total: int
    workflows_completed: int
    workflows_failed: int
    workflows_in_progress: int
    tasks_total: int
    tasks_by_state: dict[str, int]
    events_by_name: dict[str, int]
    recent_events: list[EventLogEntryResponse]

    @classmethod
    def from_domain(cls, summary: ObservabilitySummary) -> "ObservabilitySummaryResponse":
        return cls(
            agents_total=summary.agents_total,
            agents_by_state=summary.agents_by_state,
            workflows_total=summary.workflows_total,
            workflows_completed=summary.workflows_completed,
            workflows_failed=summary.workflows_failed,
            workflows_in_progress=summary.workflows_in_progress,
            tasks_total=summary.tasks_total,
            tasks_by_state=summary.tasks_by_state,
            events_by_name=summary.events_by_name,
            recent_events=[EventLogEntryResponse.from_domain(e) for e in summary.recent_events],
        )
