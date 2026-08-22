"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

نماذج حوكمة الاستقلالية. هذه النماذج تفصل تصميم القدرة وتجربتها عن قرار
ترقيتها، حتى لا يتحول توليد وكيل جديد إلى تنفيذ غير خاضع للمراجعة.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from infrastructure.agent_factory.manifest import AgentSpec
from infrastructure.cognitive_core.capability.descriptor import RiskLevel


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED_VALIDATION = "failed_validation"


@dataclass(frozen=True)
class GeneratedAgentDraft:
    """مواصفة قدرة مصممة محلياً قبل أن تتحول إلى وكيل قابل للتشغيل."""

    spec: AgentSpec
    tags: tuple[str, ...]
    risk_level: RiskLevel
    estimated_cost: float
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImprovementProposal:
    """أثر تدقيق دائم لكل محاولة توسعة ذاتية."""

    proposal_id: str
    goal_id: str
    draft: GeneratedAgentDraft
    status: ProposalStatus
    rationale: str
    validation_summary: str
    file_path: str | None = None
    reviewer_note: str | None = None


@dataclass(frozen=True)
class AutonomyPolicy:
    """الحدود المعلنة للتوسع الذاتي؛ الافتراض دائماً هو عدم الترقية التلقائية."""

    allow_agent_design: bool = True
    auto_promote_low_risk: bool = False
    max_agent_builds_per_goal: int = 1

    def may_auto_promote(self, risk_level: RiskLevel) -> bool:
        return self.auto_promote_low_risk and risk_level is RiskLevel.LOW
