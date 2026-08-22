"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

LearningLayer — ties SelfReview (step 8), KnowledgeExtractor (step 9), and
ReliabilityAdvisor (step 11) together behind one audited, identity-bound
facade, following the exact same pattern as MemoryLayer/CapabilityLayer:
CognitiveEngine depends only on this class, never on the three components
directly.

This closes the loop the master architecture doc describes for the
Cognitive Engine: every run() records episodes (already true since the
first Layer 5 increment) → learn_from_capability() reviews + extracts
knowledge from them → score_adjustment() feeds that knowledge back into the
*next* run()'s plan selection. See cognitive/engine.py for the wiring.
"""

from __future__ import annotations

from typing import Optional

from infrastructure.cognitive_core.cognitive.learning.knowledge_extraction import KnowledgeExtractor
from infrastructure.cognitive_core.cognitive.learning.reliability_advisor import ReliabilityAdvisor
from infrastructure.cognitive_core.cognitive.learning.self_review import ReviewReport, SelfReview
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog, ComponentIdentity
from infrastructure.cognitive_core.memory import MemoryLayer


class LearningLayer:
    """Facade for the Cognitive Engine's self-review / knowledge-extraction
    / plan-adjustment learning components."""

    def __init__(
        self,
        memory: MemoryLayer,
        audit_log: AppendOnlyAuditLog,
        identity: Optional[ComponentIdentity] = None,
    ):
        self.identity = identity or ComponentIdentity.create("learning_layer")
        self.memory = memory
        self._audit_log = audit_log

        self._self_review = SelfReview(memory)
        self._extractor = KnowledgeExtractor(memory)
        self._advisor = ReliabilityAdvisor(memory)

    def learn_from_capability(self, capability_id: str) -> ReviewReport:
        """Review a capability's full execution history and (re)extract its
        current reliability knowledge into Semantic Memory. Safe to call
        after every cycle — extraction is a no-op if nothing changed and
        idempotent otherwise (see KnowledgeExtractor)."""
        report = self._self_review.review_capability(capability_id)
        self._extractor.extract(report)

        self._audit_log.append(
            self.identity,
            "learning.reviewed",
            {
                "capability_id": capability_id,
                "total_runs": report.total_runs,
                "success_rate": report.success_rate,
                "failure_reasons": report.failure_reasons,
            },
        )
        return report

    def score_adjustment(self, capability_id: str) -> float:
        """The current learned plan-score adjustment for a capability, for
        use by CognitiveEngine's plan selection."""
        return self._advisor.score_adjustment(capability_id)
