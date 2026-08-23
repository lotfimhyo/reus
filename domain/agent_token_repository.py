# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.agent_token import AgentToken


class AgentTokenNotFound(Exception):
    def __init__(self, token_id: str):
        super().__init__(f"No token was found for id: {token_id}")


class AgentTokenRepository(ABC):
    @abstractmethod
    def add(self, token: AgentToken) -> None: ...

    @abstractmethod
    def get_by_hash(self, token_hash: str) -> AgentToken | None:
        """Return None when no token has this hash; verification expects that path."""
        ...

    @abstractmethod
    def list_by_agent(self, agent_id: str) -> list[AgentToken]: ...

    @abstractmethod
    def update(self, token: AgentToken) -> None: ...
