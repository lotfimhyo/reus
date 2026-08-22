# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Domain layer: AgentToken.
يمثل بيانات اعتماد (Credential) خاصة بوكيل واحد فقط، تُستخدم بديلًا عن مفتاح
API الرئيسي المشترك للسماح لوكيل بالتصرف نيابة عن نفسه فقط (لا يمكن لرمز وكيل
A انتحال شخصية وكيل B). النص الصافي للرمز لا يُخزَّن أبدًا — فقط hash أحادي
الاتجاه (راجع infrastructure/token_hashing.py)، تمامًا كأي بيانات اعتماد حقيقية.

scopes: مجموعة الصلاحيات التي يُسمح لهذا الرمز تحديدًا باستخدامها، وهي دائمًا
مجموعة جزئية (Subset) من صلاحيات الوكيل الحالية وقت التحقق — وليس وقت الإصدار
فقط. أي تقليص لاحق في صلاحيات الوكيل نفسه يُقلّص تلقائيًا الحد الأقصى الفعلي
لكل رموزه أيضًا (راجع AgentTokenService.get_effective_scopes)، حتى لو بقيت
scopes المخزَّنة هنا كما هي — دفاع متعدد الطبقات (Defense in Depth).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


class TokenAlreadyRevoked(Exception):
    def __init__(self, token_id: str):
        super().__init__(f"الرمز '{token_id}' مُلغى مسبقًا")


class ScopeExceedsAgentPermissions(Exception):
    def __init__(self, excess: frozenset[str]):
        super().__init__(f"لا يمكن منح الرمز صلاحيات لا يملكها الوكيل نفسه: {sorted(excess)}")


@dataclass
class AgentToken:
    agent_id: str
    token_hash: str  # SHA-256 للنص الصافي؛ النص الصافي نفسه لا يُحفَظ أبدًا بعد لحظة الإصدار
    label: str = ""  # وصف اختياري يساعد الوكيل/المشغّل على تمييز الرموز المتعددة
    scopes: frozenset[str] = field(default_factory=frozenset)
    token_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    revoked: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime | None = None

    def revoke(self) -> None:
        if self.revoked:
            raise TokenAlreadyRevoked(self.token_id)
        self.revoked = True

    def mark_used(self) -> None:
        self.last_used_at = datetime.now(timezone.utc)
