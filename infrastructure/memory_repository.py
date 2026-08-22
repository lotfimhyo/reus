# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
تطبيق In-Memory لمستودع الوكلاء. Thread-safe عبر قفل RLock.
هذا التطبيق مؤقت بتصميمه: أي محرك تخزين آخر (PostgreSQL, Redis) يمكن أن
يحل محله فورًا لأنه يلتزم بواجهة AgentRepository فقط (Liskov Substitution).
"""
from __future__ import annotations

import threading

from domain.entities import Agent
from domain.repositories import AgentNotFound, AgentRepository


class InMemoryAgentRepository(AgentRepository):
    def __init__(self) -> None:
        self._store: dict[str, Agent] = {}
        self._lock = threading.RLock()

    def add(self, agent: Agent) -> None:
        with self._lock:
            self._store[agent.agent_id] = agent

    def get(self, agent_id: str) -> Agent:
        with self._lock:
            agent = self._store.get(agent_id)
            if agent is None:
                raise AgentNotFound(agent_id)
            return agent

    def get_by_token_hash(self, token_hash: str) -> Agent | None:
        with self._lock:
            for agent in self._store.values():
                if agent.token_hash == token_hash:
                    return agent
            return None

    def list_all(self) -> list[Agent]:
        with self._lock:
            return list(self._store.values())

    def update(self, agent: Agent) -> None:
        with self._lock:
            if agent.agent_id not in self._store:
                raise AgentNotFound(agent.agent_id)
            self._store[agent.agent_id] = agent

    def delete(self, agent_id: str) -> None:
        with self._lock:
            if agent_id not in self._store:
                raise AgentNotFound(agent_id)
            del self._store[agent_id]
