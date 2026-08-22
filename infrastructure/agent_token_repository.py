# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

import threading

from domain.agent_token import AgentToken
from domain.agent_token_repository import AgentTokenNotFound, AgentTokenRepository


class InMemoryAgentTokenRepository(AgentTokenRepository):
    def __init__(self) -> None:
        self._store: dict[str, AgentToken] = {}
        self._lock = threading.RLock()

    def add(self, token: AgentToken) -> None:
        with self._lock:
            self._store[token.token_id] = token

    def get_by_hash(self, token_hash: str) -> AgentToken | None:
        with self._lock:
            for token in self._store.values():
                if token.token_hash == token_hash:
                    return token
            return None

    def list_by_agent(self, agent_id: str) -> list[AgentToken]:
        with self._lock:
            return [t for t in self._store.values() if t.agent_id == agent_id]

    def update(self, token: AgentToken) -> None:
        with self._lock:
            if token.token_id not in self._store:
                raise AgentTokenNotFound(token.token_id)
            self._store[token.token_id] = token
