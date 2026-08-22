# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Domain layer: TelegramLink.
يربط محادثة تلغرام واحدة (chat_id) بوكيل واحد فقط، بعد مصادقة ناجحة عبر رمز
ذلك الوكيل (AgentTokenService.authenticate) — نفس مبدأ Self-Service من الحلقة
التاسعة، عبر قناة مختلفة فقط. لا يوجد نص صافٍ أو حساس يُخزَّن هنا.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TelegramLink:
    chat_id: str
    agent_id: str
    linked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
