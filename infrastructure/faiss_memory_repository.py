# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
FAISS implementation of the semantic-memory repository.
It uses IndexFlatIP on L2-normalized vectors, which is equivalent to cosine
similarity. A distributed vector store such as Milvus or pgvector can later
replace it through the same MemoryRepository interface.
"""
from __future__ import annotations

import threading

import faiss
import numpy as np

from domain.memory import MemoryRecord
from domain.memory_repository import MemoryNotFound, MemoryRepository, SearchResult


class FaissMemoryRepository(MemoryRepository):
    def __init__(self, dimension: int) -> None:
        self._dimension = dimension
        self._index = faiss.IndexFlatIP(dimension)
        self._records: dict[str, MemoryRecord] = {}
        self._id_by_row: dict[int, str] = {}  # Index row order -> memory_id.
        self._deleted: set[str] = set()  # IndexFlatIP has no direct deletion; exclude soft-deleted entries on reads.
        self._lock = threading.RLock()

    def add(self, record: MemoryRecord, embedding: list[float]) -> None:
        vector = np.array([embedding], dtype=np.float32)
        with self._lock:
            row = self._index.ntotal
            self._index.add(vector)
            self._id_by_row[row] = record.memory_id
            self._records[record.memory_id] = record

    def get(self, memory_id: str) -> MemoryRecord:
        with self._lock:
            record = self._records.get(memory_id)
            if record is None or memory_id in self._deleted:
                raise MemoryNotFound(memory_id)
            return record

    def delete(self, memory_id: str) -> None:
        with self._lock:
            if memory_id not in self._records or memory_id in self._deleted:
                raise MemoryNotFound(memory_id)
            self._deleted.add(memory_id)  # Soft delete; exclude from search results and reads.

    def list_by_agent(self, agent_id: str) -> list[MemoryRecord]:
        with self._lock:
            return [
                r for r in self._records.values()
                if r.agent_id == agent_id and r.memory_id not in self._deleted
            ]

    def search(self, query_embedding: list[float], top_k: int, agent_id: str | None = None) -> list[SearchResult]:
        with self._lock:
            if self._index.ntotal == 0:
                return []
            # Expand k to compensate for deleted or agent-filtered entries.
            fetch_k = min(self._index.ntotal, max(top_k * 5, top_k + len(self._deleted) + 10))
            query = np.array([query_embedding], dtype=np.float32)
            scores, rows = self._index.search(query, fetch_k)

            results: list[SearchResult] = []
            for score, row in zip(scores[0], rows[0]):
                if row == -1:
                    continue
                memory_id = self._id_by_row.get(int(row))
                if memory_id is None or memory_id in self._deleted:
                    continue
                record = self._records[memory_id]
                if agent_id is not None and record.agent_id != agent_id:
                    continue
                results.append(SearchResult(record=record, score=float(score)))
                if len(results) >= top_k:
                    break
            return results
