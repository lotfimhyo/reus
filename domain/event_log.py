# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Domain layer: EventLogEntry.
Durable representation of one event published through EventBus, retained only
for observability and auditing. It is separate from business logic; EventBus
itself has no knowledge of this storage.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class EventLogEntry:
    name: str
    payload: dict
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
