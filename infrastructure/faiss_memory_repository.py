# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
تطبيق FAISS لمستودع الذاكرة الدلالية.
يستخدم IndexFlatIP (Inner Product) على متجهات مطبَّعة L2 => يعادل تشابه جيب التمام.
قابل للاستبدال لاحقًا بمخزن متجهي موزّع (Milvus, pgvector) عبر نفس واجهة MemoryRepository.
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
        self._id_by_row: dict[int, str] = {}  # ترتيب الصف في الفهرس -> memory_id
        self._deleted: set[str] = set()  # FAISS لا يدعم الحذف المباشر من IndexFlatIP؛ نتجاهل المحذوف عند البحث
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
            self._deleted.add(memory_id)  # حذف منطقي (Soft Delete)؛ يُستبعد من نتائج البحث والقراءة

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
            # نوسّع k لتعويض العناصر المحذوفة/المفلترة بحسب الوكيل
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
