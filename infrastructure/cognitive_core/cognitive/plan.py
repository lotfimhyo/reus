"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Plan generation and evaluation — steps 3 and 4 of the cognitive cycle
("توليد عدة خطط" و"تقييم كل خطة وفق: التكلفة، المخاطر...") from the master
architecture doc, section 2.5.

Design decision for this phase: each candidate capability that matches the
goal becomes its own single-step Plan. Multi-step plan composition (chaining
several capabilities together to satisfy one goal) is deliberately out of
scope here — it requires a dependency/data-flow model between steps that
belongs to a later increment, per the "no future-phase files" rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from infrastructure.cognitive_core.capability.descriptor import CapabilityDescriptor, RiskLevel

# Risk is folded into the plan score as an additive penalty on top of cost,
# so a cheap-but-risky capability doesn't automatically beat an
# expensive-but-safe one. Documented here per the master doc's requirement
# that every engineering decision states its rationale.
_RISK_PENALTY: dict[RiskLevel, float] = {
    RiskLevel.LOW: 0.0,
    RiskLevel.MEDIUM: 1.0,
    RiskLevel.HIGH: 5.0,
}


@dataclass(frozen=True)
class PlanStep:
    """A single capability invocation within a plan."""

    capability_id: str
    component_id: str
    name: str
    estimated_cost: float
    risk_level: RiskLevel

    @staticmethod
    def from_descriptor(descriptor: CapabilityDescriptor) -> "PlanStep":
        return PlanStep(
            capability_id=descriptor.capability_id,
            component_id=descriptor.component_id,
            name=descriptor.name,
            estimated_cost=descriptor.estimated_cost,
            risk_level=descriptor.risk_level,
        )


@dataclass(frozen=True)
class Plan:
    """A candidate sequence of steps that could satisfy a goal."""

    plan_id: str
    steps: tuple[PlanStep, ...]

    @property
    def total_estimated_cost(self) -> float:
        return sum(s.estimated_cost for s in self.steps)

    @property
    def max_risk_level(self) -> RiskLevel:
        return max(self.steps, key=lambda s: _RISK_PENALTY[s.risk_level]).risk_level

    @property
    def score(self) -> float:
        """Lower is better. Combines total cost with a risk penalty so plan
        selection reflects both dimensions the vision doc requires
        ("التكلفة... المخاطر")."""
        return self.total_estimated_cost + sum(
            _RISK_PENALTY[s.risk_level] for s in self.steps
        )


def generate_plans(candidates: list[CapabilityDescriptor]) -> list[Plan]:
    """
    Turn each candidate capability into a single-step plan.

    Design decision: plan_id is derived deterministically from the
    capability_id (`f"plan:{capability_id}"`), not a fresh random UUID.
    Since this phase's plans are always exactly one capability wrapped
    1:1 (see module docstring), a plan's identity is fully determined by
    *what it does* — deriving it from time-of-generation instead would
    make tie-breaking (see select_best_plan) effectively random across
    separate goal runs targeting the same capability set, which defeats
    the point of a deterministic tie-break rule.
    """
    return [
        Plan(
            plan_id=f"plan:{d.capability_id}",
            steps=(PlanStep.from_descriptor(d),),
        )
        for d in candidates
    ]


def select_best_plan(
    plans: list[Plan],
    score_adjustment: Optional[Callable[[Plan], float]] = None,
) -> Plan:
    """
    Pick the lowest-score plan. Ties broken by plan_id for determinism.

    `score_adjustment`, if given, is added on top of each plan's declared
    Plan.score — this is how learned reliability data (Layer 5's Self-
    Review / Knowledge Extraction, see cognitive/learning/) biases future
    plan selection ("تحسين أسلوب التفكير للمستقبل") without needing to
    mutate the plan's own cost/risk-based score, which stays a pure
    reflection of the capability's *declared* metadata.
    """

    def effective_score(plan: Plan) -> float:
        base = plan.score
        if score_adjustment is not None:
            base += score_adjustment(plan)
        return base

    return min(plans, key=lambda p: (effective_score(p), p.plan_id))
