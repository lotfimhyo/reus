"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Cognitive Engine (Layer 5) — learning components: Self-Review, Knowledge
Extraction, and Reliability-based plan adjustment (cognitive cycle steps
8, 9, and 11).

Public surface: CognitiveEngine and external callers should depend only on
LearningLayer, not on SelfReview/KnowledgeExtractor/ReliabilityAdvisor
directly.
"""

from infrastructure.cognitive_core.cognitive.learning.exceptions import VeritasLearningError
from infrastructure.cognitive_core.cognitive.learning.knowledge_extraction import (
    KnowledgeExtractor,
    classify_reliability,
)
from infrastructure.cognitive_core.cognitive.learning.learning_layer import LearningLayer
from infrastructure.cognitive_core.cognitive.learning.reliability_advisor import ReliabilityAdvisor
from infrastructure.cognitive_core.cognitive.learning.self_review import ReviewReport, SelfReview

__all__ = [
    "LearningLayer",
    "ReviewReport",
    "SelfReview",
    "KnowledgeExtractor",
    "classify_reliability",
    "ReliabilityAdvisor",
    "VeritasLearningError",
]
