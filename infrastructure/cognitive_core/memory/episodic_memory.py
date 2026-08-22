"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Episodic Memory — the persistent record of tasks executed and their
outcomes, per master architecture doc section 2.3.

Design decision (section 4 of the architecture doc): SQLite was chosen over
a server-based database for this phase because Local Mode requires no
separate service, and the access pattern (append + query by task/time) maps
cleanly onto a single table with indexes. Access goes through this one
Repository-pattern class, so swapping SQLite for Postgres later means
reimplementing this class without touching any caller.
"""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from infrastructure.cognitive_core.memory.exceptions import UnknownEpisodeError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_episodes_task_id ON episodes(task_id);
CREATE INDEX IF NOT EXISTS idx_episodes_created_at ON episodes(created_at);
CREATE INDEX IF NOT EXISTS idx_episodes_action ON episodes(action);
"""


@dataclass(frozen=True)
class Episode:
    """A single recorded step or outcome belonging to a task."""

    id: str
    task_id: str
    actor_id: str
    action: str
    payload: dict[str, Any]
    result: Optional[dict[str, Any]]
    created_at: str

    @staticmethod
    def _from_row(row: sqlite3.Row) -> "Episode":
        return Episode(
            id=row["id"],
            task_id=row["task_id"],
            actor_id=row["actor_id"],
            action=row["action"],
            payload=json.loads(row["payload_json"]),
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            created_at=row["created_at"],
        )


def _locked(method):
    """See semantic_memory.py's _locked docstring — same reasoning:
    this connection can be called from multiple ThreadingHTTPServer
    request threads."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class EpisodicMemory:
    """Repository for recording and querying task episodes."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @_locked
    def record(
        self,
        task_id: str,
        actor_id: str,
        action: str,
        payload: dict[str, Any],
        result: Optional[dict[str, Any]] = None,
    ) -> Episode:
        """Append a new episode. Episodic Memory is append-only by design:
        history is never edited, only extended (e.g. a correction is a new
        episode, not a mutation of an old one)."""
        episode = Episode(
            id=str(uuid.uuid4()),
            task_id=task_id,
            actor_id=actor_id,
            action=action,
            payload=payload,
            result=result,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._conn.execute(
            "INSERT INTO episodes "
            "(id, task_id, actor_id, action, payload_json, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                episode.id,
                episode.task_id,
                episode.actor_id,
                episode.action,
                json.dumps(episode.payload),
                json.dumps(episode.result) if episode.result is not None else None,
                episode.created_at,
            ),
        )
        self._conn.commit()
        return episode

    @_locked
    def get(self, episode_id: str) -> Episode:
        row = self._conn.execute(
            "SELECT * FROM episodes WHERE id = ?", (episode_id,)
        ).fetchone()
        if row is None:
            raise UnknownEpisodeError(f"No episode with id={episode_id!r}.")
        return Episode._from_row(row)

    @_locked
    def for_task(self, task_id: str) -> list[Episode]:
        """All episodes belonging to a task, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM episodes WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        return [Episode._from_row(r) for r in rows]

    @_locked
    def recent(self, limit: int = 20) -> list[Episode]:
        """Most recent episodes across all tasks, newest first."""
        rows = self._conn.execute(
            "SELECT * FROM episodes ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [Episode._from_row(r) for r in rows]

    @_locked
    def for_action(self, action: str, limit: int = 1000) -> list[Episode]:
        """All episodes with a given action, across all tasks, newest first.

        Added to support the Cognitive Engine's Self-Review step (Layer 5
        learning components): reviewing how a capability has performed
        historically requires scanning "goal.completed" /
        "goal.failed_execution" episodes across *every* past task, not just
        one — something for_task() cannot do."""
        rows = self._conn.execute(
            "SELECT * FROM episodes WHERE action = ? ORDER BY created_at DESC LIMIT ?",
            (action, limit),
        ).fetchall()
        return [Episode._from_row(r) for r in rows]

    @_locked
    def close(self) -> None:
        self._conn.close()
