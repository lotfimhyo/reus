# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Event bus: an event-driven architecture component. Every system event, such as
agent creation or a state change, is published here and automatically recorded
in structured logs to preserve the event-recording security requirement.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("reus_veritas.events")


@dataclass(frozen=True)
class Event:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


Subscriber = Callable[[Event], None]


class EventBus(ABC):
    @abstractmethod
    def publish(self, event: Event) -> None: ...

    @abstractmethod
    def subscribe(self, event_name: str, handler: Subscriber) -> None: ...


class InMemoryEventBus(EventBus):
    """Single-process in-memory Pub/Sub implementation. A Redis Pub/Sub bus
    can later replace it for multi-node distribution without application-layer
    changes because the EventBus interface remains the same."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)

    def publish(self, event: Event) -> None:
        logger.info(
            "event_published",
            extra={"event_name": event.name, "payload": event.payload, "ts": event.timestamp.isoformat()},
        )
        for handler in self._subscribers.get(event.name, []):
            handler(event)
        for handler in self._subscribers.get("*", []):
            handler(event)

    def subscribe(self, event_name: str, handler: Subscriber) -> None:
        self._subscribers[event_name].append(handler)
