# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Domain layer: TelegramLink.
It links exactly one Telegram chat (chat_id) to one agent after successful
authentication through that agent's token (AgentTokenService.authenticate).
No plaintext or sensitive content is stored here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TelegramLink:
    chat_id: str
    agent_id: str
    linked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
