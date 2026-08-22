# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Repository Pattern لطبقة الذاكرة الدلالية.
لا يعرف شيئًا عن FAISS أو أي محرك بحث متجهي بعينه، حتى يمكن استبداله
(مثلاً بـ pgvector أو Pinecone) دون المساس بطبقة التطبيق.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from domain.memory import MemoryRecord


class MemoryNotFound(Exception):
    def __init__(self, memory_id: str):
        super().__init__(f"لم يتم العثور على مقطع ذاكرة بالمعرّف: {memory_id}")
        self.memory_id = memory_id


@dataclass
class SearchResult:
    record: MemoryRecord
    score: float  # تشابه جيب التمام (كلما اقترب من 1 كان أكثر تشابهًا)


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
