# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Domain layer: MemoryRecord entity.
Represents one memory record that an agent can store and later retrieve through
semantic search.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


class EmptyContent(Exception):
    def __init__(self):
        super().__init__("A memory record cannot have empty content")


@dataclass
class MemoryRecord:
    agent_id: str
    content: str
    tags: list[str] = field(default_factory=list)
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise EmptyContent()
