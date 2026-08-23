# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Domain layer: AgentToken.
Represents a credential for exactly one agent. It can replace the shared primary
API key only for that agent's self-service actions; an agent A token cannot
impersonate agent B. Token plaintext is never stored—only a one-way hash, as
for any real credential.

scopes are the permissions this token may use. They are always evaluated as a
subset of the agent's current permissions at verification time, not merely at
issuance. A later reduction in an agent's permissions automatically reduces the
effective maximum for every token through AgentTokenService.get_effective_scopes,
even when the stored scopes remain unchanged. This is defense in depth.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


class TokenAlreadyRevoked(Exception):
    def __init__(self, token_id: str):
        super().__init__(f"Token '{token_id}' is already revoked")


class ScopeExceedsAgentPermissions(Exception):
    def __init__(self, excess: frozenset[str]):
        super().__init__(f"A token cannot receive permissions its agent does not have: {sorted(excess)}")


@dataclass
class AgentToken:
    agent_id: str
    token_hash: str  # SHA-256 of plaintext; plaintext is never retained after issuance.
    label: str = ""  # Optional label that distinguishes multiple tokens for an agent or operator.
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
