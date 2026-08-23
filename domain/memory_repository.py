# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Repository pattern for the semantic-memory layer. It remains independent of
FAISS and any particular vector search engine, allowing an implementation such
as pgvector or Pinecone to be substituted without changing the application layer.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from domain.memory import MemoryRecord


class MemoryNotFound(Exception):
    def __init__(self, memory_id: str):
        super().__init__(f"No memory record was found for id: {memory_id}")
        self.memory_id = memory_id


@dataclass
class SearchResult:
    record: MemoryRecord
    score: float  # Cosine similarity; values closer to 1 are more similar.


class MemoryRepository(ABC):
    @abstractmethod
    def add(self, record: MemoryRecord, embedding: list[float]) -> None: ...

    @abstractmethod
    def get(self, memory_id: str) -> MemoryRecord: ...

    @abstractmethod
    def delete(self, memory_id: str) -> None: ...

    @abstractmethod
    def list_by_agent(self, agent_id: str) -> list[MemoryRecord]: ...

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int, agent_id: str | None = None) -> list[SearchResult]: ...
