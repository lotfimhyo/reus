"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
from pathlib import Path

import pytest

from domain.autonomy import GeneratedAgentDraft, ImprovementProposal, ProposalStatus
from infrastructure.agent_factory.manifest import AgentSpec, TestCase
from infrastructure.autonomy.ledger import FileGovernanceLedger
from infrastructure.cognitive_core.capability.descriptor import RiskLevel


def _proposal() -> ImprovementProposal:
    return ImprovementProposal(
        proposal_id="proposal-1",
        goal_id="goal-1",
        draft=GeneratedAgentDraft(
            spec=AgentSpec("writer", "text.writer", "Writes text", "identity", [TestCase("x", "x")]),
            tags=("text",),
            risk_level=RiskLevel.LOW,
            estimated_cost=0.0,
        ),
        status=ProposalStatus.PENDING,
        rationale="capability gap",
        validation_summary="passed",
    )


def test_governance_record_and_review_survive_restart_with_audit(tmp_path: Path):
    store_path = tmp_path / "governance.json"
    audit_path = tmp_path / "governance.audit.jsonl"
    first = FileGovernanceLedger(str(store_path), str(audit_path))
    proposal = _proposal()
    first.record(proposal)
    proposal.status = ProposalStatus.REJECTED
    proposal.reviewer_note = "insufficient scope"
    first.update(proposal)

    restarted = FileGovernanceLedger(str(store_path), str(audit_path))
    restored = restarted.get("proposal-1")
    assert restored.status is ProposalStatus.REJECTED
    assert restored.reviewer_note == "insufficient scope"
    assert restored.draft.spec.capability == "text.writer"
    audit = audit_path.read_text(encoding="utf-8")
    assert '"event": "created"' in audit
    assert '"event": "updated"' in audit


def test_governance_ledgers_are_local_to_each_node_until_a_dedicated_raft_policy_exists(tmp_path: Path):
    node_a = FileGovernanceLedger(str(tmp_path / "node-a" / "governance.json"))
    node_b = FileGovernanceLedger(str(tmp_path / "node-b" / "governance.json"))

    node_a.record(_proposal())

    assert node_a.get("proposal-1").status is ProposalStatus.PENDING
    assert node_b.list_all() == []
    with pytest.raises(KeyError):
        node_b.get("proposal-1")
