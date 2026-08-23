# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""Application layer for memory operations.

It connects agent permissions from the domain model to semantic search
infrastructure and keeps each agent's `memory_refs` list synchronized.
"""
from __future__ import annotations

from dataclasses import dataclass

from domain.entities import PermissionDenied
from domain.memory import MemoryRecord
from domain.memory_repository import MemoryRepository, SearchResult
from domain.repositories import AgentRepository
from infrastructure.embedding import Embedder


@dataclass
class StoreMemoryCommand:
    agent_id: str
    content: str
    tags: list[str]


class MemoryService:
    def __init__(self, memory_repo: MemoryRepository, agent_repo: AgentRepository, embedder: Embedder) -> None:
        self._memory_repo = memory_repo
        self._agent_repo = agent_repo
        self._embedder = embedder

    def _require_permission(self, agent_id: str, permission: str):
        agent = self._agent_repo.get(agent_id)
        if permission not in agent.permissions:
            raise PermissionDenied(permission)
        return agent

    def store(self, cmd: StoreMemoryCommand) -> MemoryRecord:
        agent = self._require_permission(cmd.agent_id, "write:memory")
        record = MemoryRecord(agent_id=cmd.agent_id, content=cmd.content, tags=cmd.tags)
        embedding = self._embedder.embed(cmd.content)
        self._memory_repo.add(record, embedding)
        agent.memory_refs.append(record.memory_id)
        agent.record_operation(action="store_memory", result="success", memory_id=record.memory_id)
        self._agent_repo.update(agent)
        return record

    def search(self, agent_id: str, query: str, top_k: int = 5) -> list[SearchResult]:
        self._require_permission(agent_id, "read:memory")
        query_embedding = self._embedder.embed(query)
        return self._memory_repo.search(query_embedding, top_k=top_k, agent_id=agent_id)

    def list_for_agent(self, agent_id: str) -> list[MemoryRecord]:
        self._require_permission(agent_id, "read:memory")
        return self._memory_repo.list_by_agent(agent_id)

    def forget(self, agent_id: str, memory_id: str) -> None:
        agent = self._require_permission(agent_id, "write:memory")
        self._memory_repo.delete(memory_id)
        if memory_id in agent.memory_refs:
            agent.memory_refs.remove(memory_id)
        agent.record_operation(action="forget_memory", result="success", memory_id=memory_id)
        self._agent_repo.update(agent)
