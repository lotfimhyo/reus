"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

CognitiveEngine — Layer 5, the orchestration layer implementing the
cognitive cycle from the master architecture doc, section 2.5:

  1. Understand the goal       -> Goal (already structured at input)
  2. Analyze the problem       -> analyze(): query Capability Registry (Layer 4)
  3. Generate candidate plans  -> generate_plans()
  4. Evaluate every plan       -> Plan.score (cost + risk) + learned adjustment
  5. Select the best plan      -> select_best_plan()
  6. Execute                   -> injected Executor (typically Layer 2 LocalExecutor)
  7. Evaluate the result       -> ExecutionResult.success
  8. Self-review               -> LearningLayer.learn_from_capability() -> SelfReview
  9. Extract new knowledge     -> LearningLayer.learn_from_capability() -> KnowledgeExtractor
 10. Update memory             -> MemoryLayer.record_episode() (Layer 3)
 11. Improve future reasoning  -> ReliabilityAdvisor.score_adjustment(), consulted in step 4
     of every *subsequent* run() call

Steps 8/9/11 were deferred in this layer's first increment because they
needed a real population of executed goals to learn from — building them
against zero usage data would have meant guessing at an interface no one
had validated. That population now exists (every run() since has recorded
audited episodes), so this increment activates them: see
cognitive/learning/ for SelfReview, KnowledgeExtractor, and
ReliabilityAdvisor. Passing `learning=None` (the default) fully disables
steps 8/9/11 and reproduces the original, purely declarative cost/risk
scoring behavior — learning is additive, never required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from infrastructure.cognitive_core.capability import CapabilityLayer
from infrastructure.cognitive_core.cognitive.exceptions import EmptyPlanSetError, NoCapabilityFoundError
from infrastructure.cognitive_core.cognitive.execution import ExecutionResult, Executor
from infrastructure.cognitive_core.cognitive.goal import Goal
from infrastructure.cognitive_core.cognitive.learning import LearningLayer
from infrastructure.cognitive_core.cognitive.plan import Plan, generate_plans, select_best_plan
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog, ComponentIdentity
from infrastructure.cognitive_core.memory import MemoryLayer


@dataclass(frozen=True)
class CycleResult:
    """The full trace of one run through the cognitive cycle, useful both
    as the return value and as the basis for future self-review."""

    goal: Goal
    session_id: str
    candidate_plans: tuple[Plan, ...]
    chosen_plan: Plan
    execution_result: ExecutionResult
    episode_id: str


class CognitiveEngine:
    """
    Orchestrates one run of the cognitive cycle for a single Goal, wiring
    together Capability Registry (discovery), Memory (working context +
    episodic recording), and an injected Executor (actual execution).
    """

    def __init__(
        self,
        memory: MemoryLayer,
        capabilities: CapabilityLayer,
        audit_log: AppendOnlyAuditLog,
        identity: Optional[ComponentIdentity] = None,
        learning: Optional[LearningLayer] = None,
    ):
        self.identity = identity or ComponentIdentity.create("cognitive_engine")
        self.memory = memory
        self.capabilities = capabilities
        self._audit_log = audit_log
        self.learning = learning

    def analyze(self, goal: Goal) -> list:
        """Step 2: find capabilities that could satisfy this goal."""
        if goal.required_capability_name:
            candidates = self.capabilities.find_by_name(goal.required_capability_name)
        else:
            candidates = self.capabilities.discover()

        if goal.required_tags:
            required = set(goal.required_tags)
            candidates = [c for c in candidates if required <= set(c.tags)]

        return candidates

    def run(self, goal: Goal, executor: Executor) -> CycleResult:
        """Run the full cognitive cycle for `goal`, using `executor` to
        actually perform the chosen plan's step."""
        session_id = self.memory.open_session()
        self.memory.set_context(session_id, "goal", goal.description)

        candidates = self.analyze(goal)
        if not candidates:
            self.memory.record_episode(
                task_id=goal.goal_id,
                action="goal.failed_no_capability",
                payload={"description": goal.description, "required_tags": list(goal.required_tags)},
            )
            self.memory.close_session(session_id)
            raise NoCapabilityFoundError(
                f"No registered capability satisfies goal {goal.goal_id!r} "
                f"({goal.description!r})."
            )

        plans = generate_plans(candidates)
        if not plans:  # defensive; cannot actually happen if candidates is non-empty
            raise EmptyPlanSetError("generate_plans() produced zero plans.")

        score_adjustment = None
        if self.learning is not None:
            def score_adjustment(plan: Plan) -> float:  # noqa: E306
                return self.learning.score_adjustment(plan.steps[0].capability_id)

        chosen = select_best_plan(plans, score_adjustment=score_adjustment)
        self.memory.set_context(session_id, "chosen_plan_id", chosen.plan_id)
        self.memory.record_episode(
            task_id=goal.goal_id,
            action="plan.selected",
            payload={
                "plan_id": chosen.plan_id,
                "capability_id": chosen.steps[0].capability_id,
                "capability_name": chosen.steps[0].name,
                "score": chosen.score,
                "candidate_count": len(plans),
            },
        )

        result = executor(chosen.steps[0], goal.payload)

        episode = self.memory.record_episode(
            task_id=goal.goal_id,
            action="goal.completed" if result.success else "goal.failed_execution",
            payload={
                "plan_id": chosen.plan_id,
                "capability_id": chosen.steps[0].capability_id,
                "capability_name": chosen.steps[0].name,
                "input": goal.payload,
            },
            result={"success": result.success, "output": result.output, "error": result.error},
        )

        if self.learning is not None:
            # Steps 8 and 9, self-review and knowledge extraction, review this
            # capability's full history including the episode just recorded and
            # refresh learned reliability knowledge for the next run's score adjustment.
            self.learning.learn_from_capability(chosen.steps[0].capability_id)

        self._audit_log.append(
            self.identity,
            "cognitive.cycle_completed",
            {
                "goal_id": goal.goal_id,
                "plan_id": chosen.plan_id,
                "success": result.success,
                "episode_id": episode.id,
            },
        )

        self.memory.close_session(session_id)

        return CycleResult(
            goal=goal,
            session_id=session_id,
            candidate_plans=tuple(plans),
            chosen_plan=chosen,
            execution_result=result,
            episode_id=episode.id,
        )
