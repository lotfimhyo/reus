# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

import threading
from collections import Counter, deque

from domain.event_log import EventLogEntry
from domain.event_log_repository import EventLogRepository


class InMemoryEventLogRepository(EventLogRepository):
    """
    يستخدم deque محدود الحجم (maxlen) حتى لا ينمو استهلاك الذاكرة بلا حدود في نظام
    طويل التشغيل — الأحداث الأقدم تُستبعد تلقائيًا عند تجاوز السعة، وهذا مقصود:
    هذا سجل مراقبة تشغيلي قصير المدى، وليس أرشيفًا تدقيقيًا دائمًا (ذلك دور PostgreSQL).
    """

    def __init__(self, max_entries: int = 5000) -> None:
        self._entries: deque[EventLogEntry] = deque(maxlen=max_entries)
        self._lock = threading.RLock()

    def add(self, entry: EventLogEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def list_recent(self, limit: int = 100, name_filter: str | None = None) -> list[EventLogEntry]:
        with self._lock:
            items = list(self._entries)
        if name_filter:
            items = [e for e in items if e.name == name_filter]
        items.sort(key=lambda e: e.timestamp, reverse=True)
        return items[:limit]

    def count_by_name(self) -> dict[str, int]:
        with self._lock:
            return dict(Counter(e.name for e in self._entries))
