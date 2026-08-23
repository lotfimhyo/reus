# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Repository pattern: an abstract port that is independent of the storage
mechanism. Each implementation, whether in-memory or optional Postgres/Redis,
must obey this interface so implementations remain replaceable without changing
the application layer (dependency inversion).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities import Agent


class AgentNotFound(Exception):
    def __init__(self, agent_id: str):
        super().__init__(f"No agent was found for id: {agent_id}")
        self.agent_id = agent_id


class AgentRepository(ABC):
    @abstractmethod
    def add(self, agent: Agent) -> None: ...

    @abstractmethod
    def get(self, agent_id: str) -> Agent: ...

    @abstractmethod
    def list_all(self) -> list[Agent]: ...

    @abstractmethod
    def update(self, agent: Agent) -> None: ...

    @abstractmethod
    def delete(self, agent_id: str) -> None: ...
