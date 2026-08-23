# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
PostgresMemoryRepository uses pgvector for vector storage and similarity
search (cosine distance) directly in PostgreSQL. It provides the benefits of
FAISS (fast vector search) with persistence (data remains after a restart),
while implementing the same MemoryRepository interface.

Encryption at rest: raw content is encrypted through EncryptionService before
it is written and decrypted immediately when read. This remains transparent to
the domain and application layers, which always handle MemoryRecord.content as
plain text.
"""
from __future__ import annotations

from sqlalchemy import select

from domain.memory import MemoryRecord
from domain.memory_repository import MemoryNotFound, MemoryRepository, SearchResult
from infrastructure.encryption import EncryptionService
from infrastructure.postgres.models import MemoryRecordModel
from infrastructure.postgres.session import new_session


class PostgresMemoryRepository(MemoryRepository):
    def __init__(self, encryption: EncryptionService) -> None:
        self._encryption = encryption

    def _row_to_record(self, row: MemoryRecordModel) -> MemoryRecord:
        return MemoryRecord(
            agent_id=row.agent_id,
            content=self._encryption.decrypt_text(row.content_encrypted),
            tags=list(row.tags),
            memory_id=row.memory_id,
            created_at=row.created_at,
        )

    def add(self, record: MemoryRecord, embedding: list[float]) -> None:
        with new_session() as session:
            session.add(
                MemoryRecordModel(
                    memory_id=record.memory_id,
                    agent_id=record.agent_id,
                    content_encrypted=self._encryption.encrypt_text(record.content),
                    tags=record.tags,
                    embedding=embedding,
                    created_at=record.created_at,
                    deleted=False,
                )
            )
            session.commit()

    def get(self, memory_id: str) -> MemoryRecord:
        with new_session() as session:
            row = session.get(MemoryRecordModel, memory_id)
            if row is None or row.deleted:
                raise MemoryNotFound(memory_id)
            return self._row_to_record(row)

    def delete(self, memory_id: str) -> None:
        with new_session() as session:
            row = session.get(MemoryRecordModel, memory_id)
            if row is None or row.deleted:
                raise MemoryNotFound(memory_id)
            row.deleted = True  # Soft delete, matching the previous FaissMemoryRepository behavior.
            session.commit()

    def list_by_agent(self, agent_id: str) -> list[MemoryRecord]:
        with new_session() as session:
            stmt = select(MemoryRecordModel).where(
                MemoryRecordModel.agent_id == agent_id, MemoryRecordModel.deleted.is_(False)
            )
            rows = session.execute(stmt).scalars().all()
            return [self._row_to_record(r) for r in rows]

    def search(self, query_embedding: list[float], top_k: int, agent_id: str | None = None) -> list[SearchResult]:
        with new_session() as session:
            # cosine_distance = 1 - cosine_similarity; convert it to similarity
            # to preserve the existing SearchResult.score semantics.
            distance = MemoryRecordModel.embedding.cosine_distance(query_embedding)
            stmt = select(MemoryRecordModel, distance.label("distance")).where(
                MemoryRecordModel.deleted.is_(False)
            )
            if agent_id is not None:
                stmt = stmt.where(MemoryRecordModel.agent_id == agent_id)
            stmt = stmt.order_by(distance.asc()).limit(top_k)

            results = []
            for row, dist in session.execute(stmt).all():
                similarity = 1.0 - float(dist)
                results.append(SearchResult(record=self._row_to_record(row), score=similarity))
            return results
