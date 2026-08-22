"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Working Memory — the current task's live context.

Design decision (per master architecture doc, section 2.3): this is a pure
in-memory, session-scoped store. It intentionally does NOT persist to disk
and does NOT go through the audit log, because it holds transient reasoning
state (the current plan, intermediate results) that is meaningless once the
session ends — persisting or auditing it would add noise, not value.
Anything that should survive a session must be explicitly promoted to
Episodic or Semantic Memory by the Cognitive Engine (a future-phase concern).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from infrastructure.cognitive_core.memory.exceptions import UnknownSessionError


@dataclass
class _Session:
    session_id: str
    created_at: str
    context: dict[str, Any] = field(default_factory=dict)


class WorkingMemory:
    """
    A session-scoped key-value context store, held entirely in process
    memory. Multiple concurrent sessions (e.g. multiple in-flight tasks)
    are isolated from one another.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}

    def open_session(self, session_id: Optional[str] = None) -> str:
        """Start a new working-memory session and return its id."""
        sid = session_id or str(uuid.uuid4())
        self._sessions[sid] = _Session(
            session_id=sid,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return sid

    def _require_session(self, session_id: str) -> _Session:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise UnknownSessionError(
                f"No active working-memory session with id={session_id!r}."
            ) from exc

    def set(self, session_id: str, key: str, value: Any) -> None:
        session = self._require_session(session_id)
        session.context[key] = value

    def get(self, session_id: str, key: str, default: Any = None) -> Any:
        session = self._require_session(session_id)
        return session.context.get(key, default)

    def all(self, session_id: str) -> dict[str, Any]:
        """Return a shallow copy of the full context for a session."""
        session = self._require_session(session_id)
        return dict(session.context)

    def delete(self, session_id: str, key: str) -> None:
        session = self._require_session(session_id)
        session.context.pop(key, None)

    def close_session(self, session_id: str) -> None:
        """Discard a session's context entirely."""
        self._sessions.pop(session_id, None)

    def is_open(self, session_id: str) -> bool:
        return session_id in self._sessions
