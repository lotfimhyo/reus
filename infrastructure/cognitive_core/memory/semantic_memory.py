"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Semantic Memory — a minimal knowledge graph of entities and facts
(subject -> predicate -> object), per master architecture doc section 2.3.

Required capabilities from the vision doc ("منع تكرار المعرفة، ربط المعلومات،
تحديثها، استرجاعها بكفاءة"):
  - add_entity() is idempotent by (name, entity_type) — no duplicate nodes.
  - add_fact() is idempotent by (subject, predicate, object) — no duplicate
    edges; re-adding an existing fact updates its confidence/timestamp
    instead of creating a duplicate row.
  - facts_about() / query() retrieve linked information efficiently via
    indexed lookups.
"""

from __future__ import annotations

import functools
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from infrastructure.cognitive_core.memory.exceptions import UnknownEntityError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(name, entity_type)
);
CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES entities(id),
    predicate TEXT NOT NULL,
    object_id TEXT NOT NULL REFERENCES entities(id),
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(subject_id, predicate, object_id)
);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject_id);
CREATE INDEX IF NOT EXISTS idx_facts_object ON facts(object_id);
"""


@dataclass(frozen=True)
class Entity:
    id: str
    name: str
    entity_type: str
    created_at: str


@dataclass(frozen=True)
class Fact:
    id: str
    subject_id: str
    predicate: str
    object_id: str
    confidence: float
    created_at: str
    updated_at: str


def _locked(method):
    """`sqlite3` connections opened with `check_same_thread=False` are NOT
    automatically safe for concurrent use from multiple threads — this
    project's mTLS cluster server (ThreadingHTTPServer, one thread per
    request) can call into this same MemoryLayer instance from several
    threads at once, so every public entry point below serializes on the
    instance's own RLock (reentrant: e.g. add_fact() calls get_entity()
    internally, both need the lock)."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class SemanticMemory:
    """Repository for a lightweight entity/fact knowledge graph."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- Entities ---------------------------------------------------------

    @_locked
    def add_entity(self, name: str, entity_type: str) -> Entity:
        """Register an entity. Idempotent: calling this again with the same
        (name, entity_type) returns the existing entity instead of creating
        a duplicate node."""
        existing = self._get_entity_by_name(name, entity_type)
        if existing is not None:
            return existing

        entity = Entity(
            id=str(uuid.uuid4()),
            name=name,
            entity_type=entity_type,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._conn.execute(
            "INSERT INTO entities (id, name, entity_type, created_at) VALUES (?, ?, ?, ?)",
            (entity.id, entity.name, entity.entity_type, entity.created_at),
        )
        self._conn.commit()
        return entity

    @_locked
    def find_entity(self, name: str, entity_type: str) -> Optional[Entity]:
        """Public lookup by (name, entity_type); returns None if not found,
        without creating anything (unlike add_entity)."""
        return self._get_entity_by_name(name, entity_type)

    def _get_entity_by_name(self, name: str, entity_type: str) -> Optional[Entity]:
        row = self._conn.execute(
            "SELECT * FROM entities WHERE name = ? AND entity_type = ?",
            (name, entity_type),
        ).fetchone()
        return self._entity_from_row(row) if row else None

    @_locked
    def get_entity(self, entity_id: str) -> Entity:
        row = self._conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if row is None:
            raise UnknownEntityError(f"No entity with id={entity_id!r}.")
        return self._entity_from_row(row)

    @staticmethod
    def _entity_from_row(row: sqlite3.Row) -> Entity:
        return Entity(
            id=row["id"],
            name=row["name"],
            entity_type=row["entity_type"],
            created_at=row["created_at"],
        )

    # -- Facts --------------------------------------------------------------

    @_locked
    def add_fact(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        confidence: float = 1.0,
    ) -> Fact:
        """
        Link two entities with a predicate. Idempotent on
        (subject_id, predicate, object_id): re-asserting an existing fact
        updates its confidence and updated_at rather than duplicating it —
        this is the "منع تكرار المعرفة" requirement from the vision doc.
        """
        self.get_entity(subject_id)  # raises UnknownEntityError if missing
        self.get_entity(object_id)

        now = datetime.now(timezone.utc).isoformat()
        existing = self._conn.execute(
            "SELECT * FROM facts WHERE subject_id = ? AND predicate = ? AND object_id = ?",
            (subject_id, predicate, object_id),
        ).fetchone()

        if existing is not None:
            self._conn.execute(
                "UPDATE facts SET confidence = ?, updated_at = ? WHERE id = ?",
                (confidence, now, existing["id"]),
            )
            self._conn.commit()
            return self._fact_from_row(
                {**dict(existing), "confidence": confidence, "updated_at": now}
            )

        fact = Fact(
            id=str(uuid.uuid4()),
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            confidence=confidence,
            created_at=now,
            updated_at=now,
        )
        self._conn.execute(
            "INSERT INTO facts "
            "(id, subject_id, predicate, object_id, confidence, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                fact.id,
                fact.subject_id,
                fact.predicate,
                fact.object_id,
                fact.confidence,
                fact.created_at,
                fact.updated_at,
            ),
        )
        self._conn.commit()
        return fact

    @_locked
    def remove_fact(self, subject_id: str, predicate: str, object_id: str) -> bool:
        """Remove one specific fact, if it exists. Returns True if a row
        was actually deleted. Used when a relation has become stale (e.g.
        a capability's reliability label changed) rather than simply
        outdated in confidence — see KnowledgeExtractor for the case this
        exists for."""
        cursor = self._conn.execute(
            "DELETE FROM facts WHERE subject_id = ? AND predicate = ? AND object_id = ?",
            (subject_id, predicate, object_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    @_locked
    def facts_about(self, entity_id: str) -> list[Fact]:
        """All facts where entity_id is the subject or the object."""
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE subject_id = ? OR object_id = ? "
            "ORDER BY updated_at DESC",
            (entity_id, entity_id),
        ).fetchall()
        return [self._fact_from_row(r) for r in rows]

    @_locked
    def query(
        self,
        subject_id: Optional[str] = None,
        predicate: Optional[str] = None,
        object_id: Optional[str] = None,
    ) -> list[Fact]:
        """Flexible lookup: any combination of subject/predicate/object may
        be omitted as a wildcard."""
        clauses, params = [], []
        if subject_id is not None:
            clauses.append("subject_id = ?")
            params.append(subject_id)
        if predicate is not None:
            clauses.append("predicate = ?")
            params.append(predicate)
        if object_id is not None:
            clauses.append("object_id = ?")
            params.append(object_id)

        sql = "SELECT * FROM facts"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._fact_from_row(r) for r in rows]

    @staticmethod
    def _fact_from_row(row) -> Fact:
        r = row if isinstance(row, dict) else dict(row)
        return Fact(
            id=r["id"],
            subject_id=r["subject_id"],
            predicate=r["predicate"],
            object_id=r["object_id"],
            confidence=r["confidence"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    @_locked
    def close(self) -> None:
        self._conn.close()
