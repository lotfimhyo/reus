# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from domain.agent_token import AgentToken


class IssueTokenRequest(BaseModel):
    label: str = Field(default="", max_length=200)
    # None (الافتراضي): يرث الرمز كل صلاحيات الوكيل الحالية (السلوك السابق، متوافق للخلف).
    # قائمة صريحة: يُقيَّد الرمز بها فقط، ويُرفض الطلب إن تجاوزت صلاحيات الوكيل نفسه.
    scopes: list[str] | None = None


class IssuedTokenResponse(BaseModel):
    token_id: str
    plaintext: str  # يظهر مرة واحدة فقط في استجابة الإصدار؛ لا يظهر في أي مسار آخر بعدها أبدًا
    label: str
    scopes: list[str]
    created_at: datetime


class AgentTokenResponse(BaseModel):
    """بيانات وصفية فقط — لا نص صافٍ ولا hash، حتى في استجابات السرد."""

    token_id: str
    label: str
    scopes: list[str]
    revoked: bool
    created_at: datetime
    last_used_at: datetime | None

    @classmethod
    def from_domain(cls, token: AgentToken) -> "AgentTokenResponse":
        return cls(
            token_id=token.token_id,
            label=token.label,
            scopes=sorted(token.scopes),
            revoked=token.revoked,
            created_at=token.created_at,
            last_used_at=token.last_used_at,
        )
