# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.postgres.session import Base


class AgentModel(Base):
    """
    One row per agent. Compound fields (permissions, goals, operation log, and
    metrics) are stored as JSON because they belong to the same Agent aggregate
    and do not currently need independent querying.
    """

    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    goals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    memory_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    operation_log: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemoryRecordModel(Base):
    """
    One memory chunk. The pgvector embedding column enables similarity search
    directly in the database (cosine distance) without an external index.

    content_encrypted: Fernet-encrypted text, not plaintext. The name is
    intentional documentation that prevents incorrect direct reads of this
    column by tools or queries that do not pass through
    PostgresMemoryRepository, the only component holding EncryptionService for
    decryption. Known limitation: the embedding column is not encrypted (it is
    computed from plaintext before encryption to enable semantic search).
    Vectors may therefore reveal limited statistical information about content
    even when the raw text itself is encrypted.
    """

    __tablename__ = "memory_records"

    memory_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    embedding: Mapped[list] = mapped_column(Vector(384), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)


class AgentTokenModel(Base):
    """
    Token for one agent. Only token_hash (SHA-256) is stored; plaintext is
    never retained anywhere after issuance, as with real credentials such as
    passwords.
    """

    __tablename__ = "agent_tokens"

    token_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revoked: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowModel(Base):
    """
    The complete workflow, including all tasks, is stored as one JSON document
    because a workflow is the full aggregate and transaction boundary in this
    system (the established DDD Aggregate-as-Document pattern). This guarantees
    atomic updates to all task state together without partial conflicts.
    """

    __tablename__ = "workflows"

    workflow_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
