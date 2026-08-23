"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

ReliabilityAdvisor — step 11 of the cognitive cycle (improving future
reasoning). Reads the reliability knowledge KnowledgeExtractor wrote into
Semantic Memory and turns it into a score adjustment that biases future
plan selection (see cognitive/plan.py's select_best_plan `score_adjustment`
parameter) — without ever touching a capability's own declared cost/risk.

Design decision: with no observed history, the adjustment is exactly 0.0
(neutral) rather than optimistic or pessimistic. A brand-new capability
should compete on its declared cost/risk alone until it has actually been
run — the whole point of Self-Review is to only trust what has been
observed, not to guess.
"""

from __future__ import annotations

from infrastructure.cognitive_core.cognitive.learning.knowledge_extraction import (
    _CAPABILITY_ENTITY_TYPE,
    _HAS_RELIABILITY_PREDICATE,
)
from infrastructure.cognitive_core.memory import MemoryLayer

# How strongly an "unreliable" label should discourage a plan relative to
# its declared cost/risk penalties (see plan.py's _RISK_PENALTY, where a
# HIGH risk step already costs 5.0) — deliberately smaller than the top
# declared-risk penalty, so a capability with a lot of *declared* risk that
# has nonetheless proven reliable can still outrank a nominally low-risk
# capability with a poor track record, rather than learned history
# overriding declared risk outright.
_UNRELIABLE_PENALTY = 3.0
_MODERATE_PENALTY = 0.5
_RELIABLE_BONUS = -0.2  # small nudge toward capabilities with a proven track record


class ReliabilityAdvisor:
    """Converts learned reliability knowledge into a plan-scoring adjustment."""

    def __init__(self, memory: MemoryLayer):
        self.memory = memory

    def score_adjustment(self, capability_id: str) -> float:
        """Returns an additive adjustment for a capability's plan score.
        0.0 means "no learned data, no opinion"."""
        capability_entity = self.memory.find_entity(
            capability_id, _CAPABILITY_ENTITY_TYPE
        )
        if capability_entity is None:
            return 0.0

        facts = self.memory.query_facts(
            subject_id=capability_entity.id, predicate=_HAS_RELIABILITY_PREDICATE
        )
        if not facts:
            return 0.0

        label_entity = self.memory.get_entity(facts[0].object_id)
        return {
            "reliable": _RELIABLE_BONUS,
            "moderate": _MODERATE_PENALTY,
            "unreliable": _UNRELIABLE_PENALTY,
            "unproven": 0.0,
        }.get(label_entity.name, 0.0)
