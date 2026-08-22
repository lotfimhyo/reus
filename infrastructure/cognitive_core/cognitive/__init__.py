"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Layer 5 — Cognitive Engine (Orchestration).

Public surface: other layers (and the future Interface Layer) must depend
only on the symbols exported here.
"""

from infrastructure.cognitive_core.cognitive.engine import CognitiveEngine, CycleResult
from infrastructure.cognitive_core.cognitive.exceptions import (
    EmptyPlanSetError,
    NoCapabilityFoundError,
    VeritasCognitiveError,
)
from infrastructure.cognitive_core.cognitive.execution import ExecutionResult, Executor
from infrastructure.cognitive_core.cognitive.goal import Goal
from infrastructure.cognitive_core.cognitive.learning import (
    KnowledgeExtractor,
    LearningLayer,
    ReliabilityAdvisor,
    ReviewReport,
    SelfReview,
    VeritasLearningError,
)
from infrastructure.cognitive_core.cognitive.plan import Plan, PlanStep, generate_plans, select_best_plan

__all__ = [
    "CognitiveEngine",
    "CycleResult",
    "Goal",
    "Plan",
    "PlanStep",
    "generate_plans",
    "select_best_plan",
    "ExecutionResult",
    "Executor",
    "VeritasCognitiveError",
    "NoCapabilityFoundError",
    "EmptyPlanSetError",
    "LearningLayer",
    "SelfReview",
    "ReviewReport",
    "KnowledgeExtractor",
    "ReliabilityAdvisor",
    "VeritasLearningError",
]
