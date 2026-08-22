# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from application.agent_service import AgentService, RegisterAgentCommand
from application.agent_tools import AgentToolExecutor, UnknownTool
from application.memory_service import MemoryService, StoreMemoryCommand
from application.orchestrator_service import OrchestratorService
from infrastructure.embedding import HashingEmbedder
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.faiss_memory_repository import FaissMemoryRepository
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository

DIM = 128


@pytest.fixture
def agent_repo() -> InMemoryAgentRepository:
    return InMemoryAgentRepository()


@pytest.fixture
def agent_service(agent_repo) -> AgentService:
    return AgentService(repository=agent_repo, event_bus=InMemoryEventBus())


@pytest.fixture
def memory_service(agent_repo) -> MemoryService:
    return MemoryService(
        memory_repo=FaissMemoryRepository(dimension=DIM),
        agent_repo=agent_repo,
        embedder=HashingEmbedder(dimension=DIM),
    )


def test_dispatch_unknown_tool_raises(memory_service):
    executor = AgentToolExecutor(memory_service=memory_service, agent_id="a1")
    with pytest.raises(UnknownTool):
        executor.dispatch("delete_universe", {})


def test_store_memory_tool_actually_stores(agent_service, memory_service):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="tool-agent", permissions={"read:memory", "write:memory"}, goals=[])
    )
    executor = AgentToolExecutor(memory_service=memory_service, agent_id=agent.agent_id)

    result = executor.dispatch("store_memory", {"content": "ملاحظة عبر أداة", "tags": ["note"]})

    assert result["status"] == "stored"
    assert "memory_id" in result
    stored = memory_service.list_for_agent(agent.agent_id)
    assert len(stored) == 1
    assert stored[0].content == "ملاحظة عبر أداة"


def test_search_memory_tool_finds_stored_content(agent_service, memory_service):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="tool-agent", permissions={"read:memory", "write:memory"}, goals=[])
    )
    memory_service.store(StoreMemoryCommand(agent_id=agent.agent_id, content="سعر الذهب ارتفع اليوم", tags=[]))
    executor = AgentToolExecutor(memory_service=memory_service, agent_id=agent.agent_id)

    result = executor.dispatch("search_memory", {"query": "أسعار الذهب", "top_k": 3})

    assert len(result["matches"]) == 1
    assert "الذهب" in result["matches"][0]["content"]


def test_store_memory_tool_without_permission_returns_error_not_exception(agent_service, memory_service):
    """
    مهم: الأداة تُعيد رسالة خطأ داخل النتيجة (ليكتشفها النموذج ويتصرف)، بدل رفع
    استثناء يُفشل حلقة الأدوات بالكامل — سلوك متعمَّد وليس تجاهلًا للصلاحيات.
    """
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="read-only-agent", permissions={"read:memory"}, goals=[])
    )
    executor = AgentToolExecutor(memory_service=memory_service, agent_id=agent.agent_id)

    result = executor.dispatch("store_memory", {"content": "محاولة غير مصرَّح بها"})

    assert "error" in result


def test_search_memory_tool_for_unknown_agent_returns_error(memory_service):
    executor = AgentToolExecutor(memory_service=memory_service, agent_id="ghost-agent")
    result = executor.dispatch("search_memory", {"query": "أي شيء"})
    assert "error" in result


# ---------- أدوات التعاون (create_task, list_agents) ----------


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def orchestrator(agent_repo, event_bus) -> OrchestratorService:
    return OrchestratorService(workflow_repo=InMemoryWorkflowRepository(), agent_repo=agent_repo, event_bus=event_bus)


def test_collaboration_tools_unavailable_without_orchestrator(agent_service, memory_service):
    """بلا orchestrator/agent_repo، تبقى الأداتان غير معروفتين عمدًا (لا يُفترض وجودهما ضمنيًا)."""
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions={"spawn:subagent"}, goals=[]))
    executor = AgentToolExecutor(memory_service=memory_service, agent_id=agent.agent_id)

    with pytest.raises(UnknownTool):
        executor.dispatch("create_task", {"task_name": "x", "prompt": "y"})


def test_create_task_requires_spawn_permission(agent_service, memory_service, orchestrator, agent_repo):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    executor = AgentToolExecutor(
        memory_service=memory_service, agent_id=agent.agent_id, orchestrator=orchestrator, agent_repo=agent_repo
    )

    result = executor.dispatch("create_task", {"task_name": "x", "prompt": "y"})

    assert "error" in result
    assert "spawn:subagent" in result["error"]


def test_create_task_defaults_to_self_when_no_target_specified(agent_service, memory_service, orchestrator, agent_repo):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="a", permissions={"spawn:subagent"}, goals=[])
    )
    executor = AgentToolExecutor(
        memory_service=memory_service, agent_id=agent.agent_id, orchestrator=orchestrator, agent_repo=agent_repo
    )

    result = executor.dispatch("create_task", {"task_name": "خطوة-تخطيط-ذاتي", "prompt": "حلّل البيانات"})

    assert result["status"] == "created"
    assert result["assigned_to"] == agent.agent_id
    workflow = orchestrator.get_workflow(result["workflow_id"])
    task = workflow.get_task(result["task_id"])
    assert task.payload["prompt"] == "حلّل البيانات"
    assert task.agent_id == agent.agent_id


def test_create_task_delegates_to_another_agent(agent_service, memory_service, orchestrator, agent_repo):
    delegator = agent_service.register_agent(
        RegisterAgentCommand(name="delegator", permissions={"spawn:subagent"}, goals=[])
    )
    worker = agent_service.register_agent(RegisterAgentCommand(name="worker", permissions=set(), goals=[]))
    executor = AgentToolExecutor(
        memory_service=memory_service, agent_id=delegator.agent_id, orchestrator=orchestrator, agent_repo=agent_repo
    )

    result = executor.dispatch(
        "create_task", {"task_name": "مهمة-موكَلة", "prompt": "افعل كذا", "target_agent_id": worker.agent_id}
    )

    assert result["assigned_to"] == worker.agent_id
    workflow = orchestrator.get_workflow(result["workflow_id"])
    task = workflow.get_task(result["task_id"])
    assert task.agent_id == worker.agent_id


def test_create_task_with_unknown_target_agent_returns_error(agent_service, memory_service, orchestrator, agent_repo):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="a", permissions={"spawn:subagent"}, goals=[])
    )
    executor = AgentToolExecutor(
        memory_service=memory_service, agent_id=agent.agent_id, orchestrator=orchestrator, agent_repo=agent_repo
    )

    result = executor.dispatch(
        "create_task", {"task_name": "x", "prompt": "y", "target_agent_id": "ghost-agent"}
    )

    assert "error" in result


def test_list_agents_requires_spawn_permission(agent_service, memory_service, orchestrator, agent_repo):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    executor = AgentToolExecutor(
        memory_service=memory_service, agent_id=agent.agent_id, orchestrator=orchestrator, agent_repo=agent_repo
    )

    result = executor.dispatch("list_agents", {})

    assert "error" in result


def test_list_agents_returns_all_registered_agents(agent_service, memory_service, orchestrator, agent_repo):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="coordinator", permissions={"spawn:subagent"}, goals=[])
    )
    agent_service.register_agent(RegisterAgentCommand(name="helper", permissions=set(), goals=[]))
    executor = AgentToolExecutor(
        memory_service=memory_service, agent_id=agent.agent_id, orchestrator=orchestrator, agent_repo=agent_repo
    )

    result = executor.dispatch("list_agents", {})

    names = {a["name"] for a in result["agents"]}
    assert names == {"coordinator", "helper"}
