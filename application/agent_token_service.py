# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""Application layer for agent tokens.

It issues a new token only for an existing agent and only within that agent's
current permissions, lists token metadata without plaintext or hashes, revokes
tokens, and authenticates a token at HTTP boundaries through
`infrastructure/security.py`.
"""
from __future__ import annotations

from dataclasses import dataclass

from domain.agent_token import AgentToken, ScopeExceedsAgentPermissions
from domain.agent_token_repository import AgentTokenNotFound, AgentTokenRepository
from domain.repositories import AgentRepository
from infrastructure.token_hashing import generate_plaintext_token, hash_token


@dataclass
class IssuedToken:
    token: AgentToken
    plaintext: str  # Returned once to the caller and never stored after that moment.


class AgentTokenService:
    def __init__(self, token_repo: AgentTokenRepository, agent_repo: AgentRepository) -> None:
        self._tokens = token_repo
        self._agents = agent_repo

    def issue_token(self, agent_id: str, label: str = "", scopes: set[str] | None = None) -> IssuedToken:
        agent = self._agents.get(agent_id)  # Raises AgentNotFound when the agent does not exist.

        if scopes is None:
            # No explicit scopes: inherit all current agent permissions for backward compatibility.
            effective_scopes = frozenset(agent.permissions)
        else:
            requested = frozenset(scopes)
            excess = requested - agent.permissions
            if excess:
                raise ScopeExceedsAgentPermissions(excess)
            effective_scopes = requested

        plaintext = generate_plaintext_token()
        token = AgentToken(agent_id=agent_id, token_hash=hash_token(plaintext), label=label, scopes=effective_scopes)
        self._tokens.add(token)
        return IssuedToken(token=token, plaintext=plaintext)

    def list_tokens(self, agent_id: str) -> list[AgentToken]:
        self._agents.get(agent_id)
        return self._tokens.list_by_agent(agent_id)

    def revoke_token(self, agent_id: str, token_id: str) -> AgentToken:
        matching = [t for t in self._tokens.list_by_agent(agent_id) if t.token_id == token_id]
        if not matching:
            raise AgentTokenNotFound(token_id)
        token = matching[0]
        token.revoke()
        self._tokens.update(token)
        return token

    def authenticate(self, plaintext: str) -> AgentToken | None:
        """Authenticate a token supplied by an HTTP request. Return None for a
        missing or revoked token because this is a repeated network-boundary
        check, not an internal exceptional condition."""
        token = self._tokens.get_by_hash(hash_token(plaintext))
        if token is None or token.revoked:
            return None
        token.mark_used()
        self._tokens.update(token)
        return token

    def get_effective_scopes(self, token: AgentToken) -> frozenset[str]:
        """Intersect stored token scopes with the agent's **current** permissions.

        Reducing an agent's permissions therefore also reduces every older
        token's effective authority without requiring token reissuance.
        """
        agent = self._agents.get(token.agent_id)
        return token.scopes & agent.permissions
