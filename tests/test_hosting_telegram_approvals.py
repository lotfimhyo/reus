"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
from application.hosting_telegram_approvals import HostingTelegramApprovalWorkflow
from application.telegram_service import TelegramService
from infrastructure.agent_token_repository import InMemoryAgentTokenRepository
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.hosting_governance import HostingOffer, HostingPurchaseGate
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.telegram_link_repository import InMemoryTelegramLinkRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository
from application.agent_token_service import AgentTokenService
from application.orchestrator_service import OrchestratorService


def _telegram() -> TelegramService:
    repository = InMemoryAgentRepository()
    bus = InMemoryEventBus()
    return TelegramService(
        link_repo=InMemoryTelegramLinkRepository(),
        token_service=AgentTokenService(token_repo=InMemoryAgentTokenRepository(), agent_repo=repository),
        orchestrator=OrchestratorService(workflow_repo=InMemoryWorkflowRepository(), agent_repo=repository, event_bus=bus),
        event_bus=bus,
        admin_chat_ids=frozenset({"owner", "other-admin"}),
    )


def _offer() -> HostingOffer:
    return HostingOffer(
        offer_id="official-provider-small", provider="Official Provider", plan="Small", region="eu-west",
        monthly_price_minor=1200, currency="EUR", billing_period="monthly", is_free=False,
        data_boundary="EU", compute_summary="2 vCPU / 4 GB RAM",
    )


def test_hosting_approval_is_bound_to_requesting_admin_and_describes_cost():
    telegram = _telegram()
    delivered: list[tuple[str, str]] = []
    telegram.set_delivery_callback(lambda chat_id, text: delivered.append((chat_id, text)))
    workflow = HostingTelegramApprovalWorkflow(telegram, HostingPurchaseGate())
    authorization = workflow.request("owner", _offer())

    assert "1200 EUR / monthly" in delivered[-1][1]
    telegram.handle_incoming_message("other-admin", f"/approve {authorization.authorization_id}")
    assert workflow.resolved(authorization.authorization_id) is None
    telegram.handle_incoming_message("owner", f"/approve {authorization.authorization_id}")
    assert workflow.resolved(authorization.authorization_id).approved
