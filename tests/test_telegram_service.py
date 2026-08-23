# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest
import time

from application.agent_service import AgentService, RegisterAgentCommand
from application.agent_token_service import AgentTokenService
from application.orchestrator_service import CreateWorkflowCommand, OrchestratorService
from application.telegram_service import TelegramService
from domain.workflow import TaskSpec
from infrastructure.agent_token_repository import InMemoryAgentTokenRepository
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.telegram_link_repository import InMemoryTelegramLinkRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def agent_repo() -> InMemoryAgentRepository:
    return InMemoryAgentRepository()


@pytest.fixture
def agent_service(agent_repo, event_bus) -> AgentService:
    return AgentService(repository=agent_repo, event_bus=event_bus)


@pytest.fixture
def token_service(agent_repo) -> AgentTokenService:
    return AgentTokenService(token_repo=InMemoryAgentTokenRepository(), agent_repo=agent_repo)


@pytest.fixture
def orchestrator(agent_repo, event_bus) -> OrchestratorService:
    return OrchestratorService(workflow_repo=InMemoryWorkflowRepository(), agent_repo=agent_repo, event_bus=event_bus)


@pytest.fixture
def telegram(token_service, orchestrator, event_bus) -> TelegramService:
    service = TelegramService(
        link_repo=InMemoryTelegramLinkRepository(),
        token_service=token_service,
        orchestrator=orchestrator,
        event_bus=event_bus,
    )
    service.start()
    return service


def test_message_before_linking_prompts_to_link(telegram: TelegramService):
    reply = telegram.handle_incoming_message("chat-1", "مرحبًا")
    assert "link" in reply


def test_link_with_invalid_token_rejected(telegram: TelegramService):
    reply = telegram.handle_incoming_message("chat-1", "/link rvos_not-a-real-token")
    assert "invalid or revoked" in reply


def test_link_with_valid_token_succeeds(telegram: TelegramService, agent_service, token_service):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    issued = token_service.issue_token(agent.agent_id)

    reply = telegram.handle_incoming_message("chat-1", f"/link {issued.plaintext}")

    assert agent.agent_id in reply


def test_message_after_linking_creates_task_and_returns_ack(
    telegram: TelegramService, agent_service, token_service
):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="a", permissions={"read:memory", "write:memory"}, goals=[])
    )
    issued = token_service.issue_token(agent.agent_id)
    telegram.handle_incoming_message("chat-1", f"/link {issued.plaintext}")

    reply = telegram.handle_incoming_message("chat-1", "لخّص لي آخر الأخبار")

    assert "being processed" in reply


def test_unlink_removes_binding(telegram: TelegramService, agent_service, token_service):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    issued = token_service.issue_token(agent.agent_id)
    telegram.handle_incoming_message("chat-1", f"/link {issued.plaintext}")

    telegram.handle_incoming_message("chat-1", "/unlink")
    reply = telegram.handle_incoming_message("chat-1", "أي رسالة")

    assert "link" in reply


def test_task_completion_delivers_result_to_correct_chat(
    telegram: TelegramService, agent_service, token_service, orchestrator
):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    issued = token_service.issue_token(agent.agent_id)
    telegram.handle_incoming_message("chat-42", f"/link {issued.plaintext}")

    delivered = []
    telegram.set_delivery_callback(lambda chat_id, text: delivered.append((chat_id, text)))

    telegram.handle_incoming_message("chat-42", "ما هو سعر الذهب؟")

    workflow = orchestrator.list_workflows()[0]
    task_id = next(iter(workflow.tasks.keys()))
    orchestrator.start_task(workflow.workflow_id, task_id)
    orchestrator.complete_task(workflow.workflow_id, task_id, result={"response": "الذهب مستقر اليوم"})

    assert len(delivered) == 1
    assert delivered[0][0] == "chat-42"
    assert "الذهب مستقر اليوم" in delivered[0][1]


def test_task_failure_delivers_error_to_correct_chat(
    telegram: TelegramService, agent_service, token_service, orchestrator
):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    issued = token_service.issue_token(agent.agent_id)
    telegram.handle_incoming_message("chat-7", f"/link {issued.plaintext}")

    delivered = []
    telegram.set_delivery_callback(lambda chat_id, text: delivered.append((chat_id, text)))

    telegram.handle_incoming_message("chat-7", "مهمة ستفشل")

    workflow = orchestrator.list_workflows()[0]
    task_id = next(iter(workflow.tasks.keys()))
    orchestrator.start_task(workflow.workflow_id, task_id)
    orchestrator.fail_task(workflow.workflow_id, task_id, error="تعذّر الوصول للنموذج")

    assert len(delivered) == 1
    assert delivered[0][0] == "chat-7"
    assert "Task failed" in delivered[0][1]


def test_unrelated_task_events_do_not_trigger_delivery(telegram: TelegramService, orchestrator):
    """Task events not originating from Telegram, with no recorded chat_id,
    must not trigger any delivery attempt."""
    delivered = []
    telegram.set_delivery_callback(lambda chat_id, text: delivered.append((chat_id, text)))

    workflow = orchestrator.create_workflow(CreateWorkflowCommand(name="not-telegram", tasks=[TaskSpec(name="x")]))
    task_id = next(iter(workflow.tasks.keys()))
    orchestrator.start_task(workflow.workflow_id, task_id)
    orchestrator.complete_task(workflow.workflow_id, task_id)

    assert delivered == []


def test_sensitive_approval_is_bound_to_the_admin_chat_that_requested_it(token_service, orchestrator, event_bus):
    service = TelegramService(
        link_repo=InMemoryTelegramLinkRepository(),
        token_service=token_service,
        orchestrator=orchestrator,
        event_bus=event_bus,
        admin_chat_ids=frozenset({"admin-a", "admin-b"}),
    )
    delivered, executed = [], []
    service.set_delivery_callback(lambda chat_id, text: delivered.append((chat_id, text)))
    service.request_approval("admin-a", "operation-1", "قرار حساس", lambda: executed.append(True), lambda: None)

    service.handle_incoming_message("admin-b", "/approve operation-1")
    assert executed == []
    assert "another administrative chat" in delivered[-1][1]

    service.handle_incoming_message("admin-a", "/approve operation-1")
    assert executed == [True]


def test_sensitive_approval_expires_fail_closed(token_service, orchestrator, event_bus):
    service = TelegramService(
        link_repo=InMemoryTelegramLinkRepository(),
        token_service=token_service,
        orchestrator=orchestrator,
        event_bus=event_bus,
        admin_chat_ids=frozenset({"admin"}),
        approval_ttl_seconds=0.001,
    )
    delivered, executed = [], []
    service.set_delivery_callback(lambda chat_id, text: delivered.append((chat_id, text)))
    service.request_approval("admin", "operation-expiring", "قرار حساس", lambda: executed.append(True), lambda: None)
    time.sleep(0.01)

    service.handle_incoming_message("admin", "/approve operation-expiring")
    assert executed == []
    assert "expired" in delivered[-1][1]
