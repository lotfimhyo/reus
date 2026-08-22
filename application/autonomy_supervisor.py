"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

مشرف الاستقلالية: يربط دورة الإدراك بمصنع الوكلاء والحوكمة. لا ينفذ ترقية
لقدرة جديدة لمجرد أن النموذج اقترحها؛ كل قدرة تمر بالتصميم والتحليل الساكن
والعزل، ثم تصبح اقتراحاً قابلاً للمراجعة أو ترقية منخفضة المخاطر صريحة.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from domain.autonomy import AutonomyPolicy, GeneratedAgentDraft, ImprovementProposal, ProposalStatus
from infrastructure.agent_factory.builder import AgentBuilder, BuildResult
from infrastructure.capability_binder import AgentCapabilityBinder
from infrastructure.cognitive_core.cognitive.engine import CognitiveEngine, CycleResult
from infrastructure.cognitive_core.cognitive.exceptions import NoCapabilityFoundError
from infrastructure.cognitive_core.cognitive.execution import Executor
from infrastructure.cognitive_core.cognitive.goal import Goal


class AgentDesignProvider(Protocol):
    """مزود محلي يحول فجوة قدرة إلى مواصفة قابلة للاختبار، لا إلى كود موثوق."""

    def design(self, goal: Goal) -> GeneratedAgentDraft: ...


class GovernanceLedger(Protocol):
    """منفذ تخزين الاقتراحات، يمكن ربطه بقاعدة محلية أو بسجل تشغيل خارجي."""

    def record(self, proposal: ImprovementProposal) -> None: ...

    def get(self, proposal_id: str) -> ImprovementProposal: ...

    def update(self, proposal: ImprovementProposal) -> None: ...

    def status_counts(self) -> dict[str, int]: ...

    def list_pending(self) -> list[ImprovementProposal]: ...


@dataclass(frozen=True)
class AutonomyOutcome:
    state: str
    cycle: CycleResult | None = None
    proposal: ImprovementProposal | None = None


class AutonomySupervisor:
    """ينفذ الهدف أو يحول فجوة القدرة إلى اقتراح توسعة محكوم."""

    def __init__(
        self,
        cognitive_engine: CognitiveEngine,
        agent_builder: AgentBuilder,
        designer: AgentDesignProvider,
        governance: GovernanceLedger,
        binder: AgentCapabilityBinder,
        policy: AutonomyPolicy | None = None,
    ) -> None:
        self._engine = cognitive_engine
        self._builder = agent_builder
        self._designer = designer
        self._governance = governance
        self._binder = binder
        self._policy = policy or AutonomyPolicy()
        self._builds_by_goal: dict[str, int] = {}
        self._build_artifacts: dict[str, BuildResult] = {}

    def pursue(self, goal: Goal, executor: Executor) -> AutonomyOutcome:
        """شغّل الهدف، وصمم مسودة وكيل فقط إذا برهنت دورة الإدراك غياب القدرة."""
        try:
            return AutonomyOutcome(state="executed", cycle=self._engine.run(goal, executor))
        except NoCapabilityFoundError:
            return self._handle_capability_gap(goal)

    def _handle_capability_gap(self, goal: Goal) -> AutonomyOutcome:
        previous_builds = self._builds_by_goal.get(goal.goal_id, 0)
        if not self._policy.allow_agent_design or previous_builds >= self._policy.max_agent_builds_per_goal:
            return AutonomyOutcome(state="capability_gap")

        self._builds_by_goal[goal.goal_id] = previous_builds + 1
        draft = self._designer.design(goal)
        build = self._builder.build(draft.spec)
        proposal = self._new_proposal(goal, draft, build)
        self._governance.record(proposal)
        if build.approved:
            self._build_artifacts[proposal.proposal_id] = build

        if build.approved and self._policy.may_auto_promote(draft.risk_level):
            self.approve(proposal.proposal_id, reviewer_note="auto-promoted under low-risk policy")
            proposal = self._governance.get(proposal.proposal_id)
            return AutonomyOutcome(state="promoted", proposal=proposal)
        return AutonomyOutcome(state="proposal_created", proposal=proposal)

    def approve(self, proposal_id: str, reviewer_note: str | None = None) -> ImprovementProposal:
        """انشر قدرة اجتازت العزل بعد قرار صريح من المطور أو سياسة منخفضة المخاطر."""
        proposal = self._governance.get(proposal_id)
        if proposal.status is not ProposalStatus.PENDING:
            raise ValueError("only pending proposals may be approved")
        build = self._build_artifacts.get(proposal_id)
        if build is None or not build.approved:
            raise ValueError("approved build artifact is required for activation")
        descriptor = self._binder.bind(build)
        proposal.status = ProposalStatus.APPROVED
        proposal.reviewer_note = reviewer_note or f"published capability {descriptor.capability_id}"
        self._governance.update(proposal)
        return proposal

    def reject(self, proposal_id: str, reviewer_note: str) -> ImprovementProposal:
        proposal = self._governance.get(proposal_id)
        if proposal.status is not ProposalStatus.PENDING:
            raise ValueError("only pending proposals may be rejected")
        proposal.status = ProposalStatus.REJECTED
        proposal.reviewer_note = reviewer_note
        self._governance.update(proposal)
        return proposal

    @staticmethod
    def _new_proposal(goal: Goal, draft: GeneratedAgentDraft, build: BuildResult) -> ImprovementProposal:
        return ImprovementProposal(
            proposal_id=str(uuid.uuid4()),
            goal_id=goal.goal_id,
            draft=draft,
            status=ProposalStatus.PENDING if build.approved else ProposalStatus.FAILED_VALIDATION,
            rationale=f"No registered capability satisfied goal {goal.goal_id}.",
            validation_summary=build.reason,
            file_path=build.file_path,
        )
