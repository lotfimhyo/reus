# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.event_log import EventLogEntry


class EventLogRepository(ABC):
    @abstractmethod
    def add(self, entry: EventLogEntry) -> None: ...

    @abstractmethod
    def list_recent(self, limit: int = 100, name_filter: str | None = None) -> list[EventLogEntry]:
        """Return newest entries first, in descending timestamp order."""
        ...

    @abstractmethod
    def count_by_name(self) -> dict[str, int]:
        """Return recorded-event counts by event name for a quick summary."""
        ...
