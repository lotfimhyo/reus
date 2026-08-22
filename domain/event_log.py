# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Domain layer: EventLogEntry.
تمثيل دائم لحدث واحد نُشر عبر EventBus، محفوظ لأغراض المراقبة والتدقيق فقط
(لا علاقة له بمنطق الأعمال؛ EventBus نفسه لا يعرف بوجود هذا التخزين إطلاقًا).
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
