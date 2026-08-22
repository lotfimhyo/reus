"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
"""

from application.autonomy_telegram_commands import AutonomyTelegramCommands
from domain.autonomy import ImprovementProposal, ProposalStatus
from infrastructure.agent_factory.manifest import AgentSpec, TestCase
from domain.autonomy import GeneratedAgentDraft
from infrastructure.cognitive_core.capability.descriptor import RiskLevel


class Telegram:
    def __init__(self):
        self.commands = {}
        self.deliveries = []
        self.approvals = []

    def register_admin_command(self, command, handler):
        self.commands[command] = handler

    def deliver(self, chat_id, text):
        self.deliveries.append((chat_id, text))

    def request_approval(self, chat_id, approval_id, text, on_approve, on_reject):
        self.approvals.append((chat_id, approval_id, text, on_approve, on_reject))


def proposal():
    draft = GeneratedAgentDraft(
        spec=AgentSpec("a", "text.a", "A capability", "identity", [TestCase("a", "a")]),
        tags=("text",), risk_level=RiskLevel.LOW, estimated_cost=0.0,
    )
    return ImprovementProposal("p-1", "g-1", draft, ProposalStatus.PENDING, "gap", "passed")


class Ledger:
    def __init__(self, value):
        self.value = value

    def list_pending(self):
        return [self.value]

    def get(self, proposal_id):
        if proposal_id != self.value.proposal_id:
            raise KeyError(proposal_id)
        return self.value


class Supervisor:
    def __init__(self, value):
        self.value = value
        self.approved = []
        self.rejected = []

    def approve(self, proposal_id, reviewer_note=None):
        self.approved.append((proposal_id, reviewer_note))
        self.value.status = ProposalStatus.APPROVED
        return self.value

    def reject(self, proposal_id, reviewer_note):
        self.rejected.append((proposal_id, reviewer_note))
        self.value.status = ProposalStatus.REJECTED
        return self.value


def test_registers_commands_and_lists_pending_proposals():
    telegram, value = Telegram(), proposal()
    AutonomyTelegramCommands(Supervisor(value), Ledger(value), telegram)

    telegram.commands["/autonomy_pending"]("chat", "")

    assert "/autonomy_approve" in telegram.commands
    assert "p-1" in telegram.deliveries[-1][1]


def test_approve_requests_double_confirmation_before_promotion():
    telegram, value = Telegram(), proposal()
    supervisor = Supervisor(value)
    AutonomyTelegramCommands(supervisor, Ledger(value), telegram)

    telegram.commands["/autonomy_approve"]("chat", "p-1")
    assert not supervisor.approved
    telegram.approvals[0][3]()

    assert supervisor.approved == [("p-1", "approved through Telegram")]
