"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

MemoryLayer — the single public entry point for Layer 3 (Memory), per the
master architecture doc's "no leaky abstractions" rule: other layers must
depend only on this facade, never import WorkingMemory / EpisodicMemory /
SemanticMemory directly.

Every write to Episodic or Semantic memory is signed by this layer's own
ComponentIdentity and recorded in the shared AppendOnlyAuditLog (Layer 1),
satisfying the master doc's requirement that every operation be traceable.
Working Memory writes are excluded from the audit log by design (see
working_memory.py docstring) since they are transient reasoning state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from infrastructure.cognitive_core.identity import AppendOnlyAuditLog, ComponentIdentity
from infrastructure.cognitive_core.memory.episodic_memory import Episode, EpisodicMemory
from infrastructure.cognitive_core.memory.semantic_memory import Entity, Fact, SemanticMemory
from infrastructure.cognitive_core.memory.working_memory import WorkingMemory


class MemoryLayer:
    """Facade combining Working, Episodic, and Semantic memory behind one
    audited, identity-bound interface."""

    def __init__(
        self,
        audit_log: AppendOnlyAuditLog,
        data_dir: str | Path = "data",
        identity: Optional[ComponentIdentity] = None,
    ):
        self.identity = identity or ComponentIdentity.create("memory_layer")
        self._audit_log = audit_log

        data_dir = Path(data_dir)
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory(data_dir / "episodic.db")
        self.semantic = SemanticMemory(data_dir / "semantic.db")

    # -- Working Memory passthrough (not audited — see module docstring) --

    def open_session(self, session_id: Optional[str] = None) -> str:
        return self.working.open_session(session_id)

    def set_context(self, session_id: str, key: str, value: Any) -> None:
        self.working.set(session_id, key, value)

    def get_context(self, session_id: str, key: str, default: Any = None) -> Any:
        return self.working.get(session_id, key, default)

    def close_session(self, session_id: str) -> None:
        self.working.close_session(session_id)

    # -- Episodic Memory (audited) -----------------------------------------

    def record_episode(
        self,
        task_id: str,
        action: str,
        payload: dict[str, Any],
        result: Optional[dict[str, Any]] = None,
    ) -> Episode:
        episode = self.episodic.record(
            task_id=task_id,
            actor_id=self.identity.component_id,
            action=action,
            payload=payload,
            result=result,
        )
        self._audit_log.append(
            self.identity,
            "memory.episodic.record",
            {"episode_id": episode.id, "task_id": task_id, "action": action},
        )
        return episode

    def episodes_for_task(self, task_id: str) -> list[Episode]:
        return self.episodic.for_task(task_id)

    def episodes_by_action(self, action: str, limit: int = 1000) -> list[Episode]:
        return self.episodic.for_action(action, limit)

    def recent_episodes(self, limit: int = 20) -> list[Episode]:
        return self.episodic.recent(limit)

    # -- Semantic Memory (audited) ------------------------------------------

    def add_entity(self, name: str, entity_type: str) -> Entity:
        entity = self.semantic.add_entity(name, entity_type)
        self._audit_log.append(
            self.identity,
            "memory.semantic.add_entity",
            {"entity_id": entity.id, "name": name, "entity_type": entity_type},
        )
        return entity

    def find_entity(self, name: str, entity_type: str) -> Optional[Entity]:
        """Look up an entity by (name, entity_type) without creating it.
        Returns None if it does not exist yet. Read-only, so — like other
        lookups in this facade — not audited."""
        return self.semantic.find_entity(name, entity_type)

    def get_entity(self, entity_id: str) -> Entity:
        """Look up an entity by id. Raises UnknownEntityError if missing."""
        return self.semantic.get_entity(entity_id)

    def add_fact(
        self, subject_id: str, predicate: str, object_id: str, confidence: float = 1.0
    ) -> Fact:
        fact = self.semantic.add_fact(subject_id, predicate, object_id, confidence)
        self._audit_log.append(
            self.identity,
            "memory.semantic.add_fact",
            {
                "fact_id": fact.id,
                "subject_id": subject_id,
                "predicate": predicate,
                "object_id": object_id,
            },
        )
        return fact

    def facts_about(self, entity_id: str) -> list[Fact]:
        return self.semantic.facts_about(entity_id)

    def remove_fact(self, subject_id: str, predicate: str, object_id: str) -> bool:
        removed = self.semantic.remove_fact(subject_id, predicate, object_id)
        if removed:
            self._audit_log.append(
                self.identity,
                "memory.semantic.remove_fact",
                {"subject_id": subject_id, "predicate": predicate, "object_id": object_id},
            )
        return removed

    def query_facts(
        self,
        subject_id: Optional[str] = None,
        predicate: Optional[str] = None,
        object_id: Optional[str] = None,
    ) -> list[Fact]:
        return self.semantic.query(subject_id, predicate, object_id)

    # -- Lifecycle -----------------------------------------------------------

    def close(self) -> None:
        self.episodic.close()
        self.semantic.close()
