"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

KnowledgeExtractor — step 9 of the cognitive cycle ("استخراج المعرفة
الجديدة"). Turns a SelfReview ReviewReport into a durable Semantic Memory
fact, so a capability's *observed* reliability becomes queryable knowledge
alongside whatever it merely *declared* in its CapabilityDescriptor.

Design decision: reliability is stored as a discrete label entity
("reliable" / "moderate" / "unreliable" / "unproven") linked via a
"has_reliability" fact, rather than as a raw float. Semantic Memory's model
is entities-and-relations (per master doc section 2.3, "الذاكرة الدلالية"),
not a metrics store — a label is a first-class concept other components can
later reason about or query by name ("find all unreliable capabilities"),
which a bare number is not. The exact success_rate is not lost: it is kept
as the fact's `confidence`, so precision is still available to anything
that wants it.

Re-extracting for a capability that already has a recorded reliability does
not create a duplicate fact — it updates the existing one's confidence and
timestamp, and re-links to a different label entity if the classification
has changed. This reuses Semantic Memory's existing "no duplicate
knowledge" guarantee (see memory/semantic_memory.py) rather than
reimplementing deduplication here.
"""

from __future__ import annotations

from typing import Optional

from infrastructure.cognitive_core.cognitive.learning.self_review import ReviewReport
from infrastructure.cognitive_core.memory import Fact, MemoryLayer

_CAPABILITY_ENTITY_TYPE = "capability"
_RELIABILITY_ENTITY_TYPE = "reliability_label"
_HAS_RELIABILITY_PREDICATE = "has_reliability"

# Thresholds are a documented, adjustable policy choice, not a law of
# nature: with few observations, being conservative (biasing toward
# "moderate"/"unproven") matters more than the exact cutoff values.
_RELIABLE_THRESHOLD = 0.8
_UNRELIABLE_THRESHOLD = 0.5
_MIN_RUNS_FOR_CONFIDENT_LABEL = 3


def classify_reliability(report: ReviewReport) -> str:
    """Map a ReviewReport to a discrete reliability label."""
    if report.total_runs == 0 or report.success_rate is None:
        return "unproven"
    if report.total_runs < _MIN_RUNS_FOR_CONFIDENT_LABEL:
        return "moderate"  # too few samples to be confident either way
    if report.success_rate >= _RELIABLE_THRESHOLD:
        return "reliable"
    if report.success_rate < _UNRELIABLE_THRESHOLD:
        return "unreliable"
    return "moderate"


class KnowledgeExtractor:
    """Writes a ReviewReport into Semantic Memory as a queryable fact."""

    def __init__(self, memory: MemoryLayer):
        self.memory = memory

    def extract(self, report: ReviewReport) -> Optional[Fact]:
        """Returns None if there is nothing yet to learn (zero runs
        observed) — extracting knowledge from an empty report would just
        assert "unproven" over and over, which is not new knowledge."""
        if report.total_runs == 0:
            return None

        capability_entity = self.memory.add_entity(
            report.capability_id, _CAPABILITY_ENTITY_TYPE
        )
        label = classify_reliability(report)
        label_entity = self.memory.add_entity(label, _RELIABILITY_ENTITY_TYPE)

        # If a previous review classified this capability under a
        # *different* label, that old fact is now stale and would
        # otherwise sit alongside the new one, contradicting it — prune it
        # before recording the current classification.
        existing = self.memory.query_facts(
            subject_id=capability_entity.id, predicate=_HAS_RELIABILITY_PREDICATE
        )
        for fact in existing:
            if fact.object_id != label_entity.id:
                self.memory.remove_fact(
                    capability_entity.id, _HAS_RELIABILITY_PREDICATE, fact.object_id
                )

        return self.memory.add_fact(
            subject_id=capability_entity.id,
            predicate=_HAS_RELIABILITY_PREDICATE,
            object_id=label_entity.id,
            confidence=report.success_rate or 0.0,
        )
