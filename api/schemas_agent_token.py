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
    # None (default): inherit all current agent permissions for backward compatibility.
    # Explicit list: limit the token to those scopes and reject scopes above the agent's permissions.
    scopes: list[str] | None = None


class IssuedTokenResponse(BaseModel):
    token_id: str
    plaintext: str  # Returned once at issuance and never exposed by another endpoint.
    label: str
    scopes: list[str]
    created_at: datetime


class AgentTokenResponse(BaseModel):
    """Metadata only; never return plaintext or a token hash, including list responses."""

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
