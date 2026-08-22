# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from application.agent_service import AgentService, RegisterAgentCommand
from application.memory_service import MemoryService, StoreMemoryCommand
from application.task_executor import TaskExecutionError
from domain.workflow import TaskNode
from infrastructure.default_task_executor import DefaultTaskExecutor
from infrastructure.embedding import HashingEmbedder
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.faiss_memory_repository import FaissMemoryRepository
from infrastructure.memory_repository import InMemoryAgentRepository

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


@pytest.fixture
def executor(agent_service, memory_service) -> DefaultTaskExecutor:
    return DefaultTaskExecutor(agent_service=agent_service, memory_service=memory_service)


def test_execute_without_agent_raises(executor: DefaultTaskExecutor):
    task = TaskNode(name="orphan-task", agent_id=None)
    with pytest.raises(TaskExecutionError):
        executor.execute(task)


def test_execute_with_unknown_agent_raises(executor: DefaultTaskExecutor):
    task = TaskNode(name="t", agent_id="ghost-agent")
    with pytest.raises(TaskExecutionError):
        executor.execute(task)


def test_execute_stores_summary_when_write_permitted(executor: DefaultTaskExecutor, agent_service, memory_service):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="worker-1", permissions={"read:memory", "write:memory"}, goals=[])
    )
    task = TaskNode(name="analyze-report", agent_id=agent.agent_id)
    result = executor.execute(task)

    assert result["task_name"] == "analyze-report"
    stored = memory_service.list_for_agent(agent.agent_id)
    assert len(stored) == 1
    assert "analyze-report" in stored[0].content


def test_execute_uses_relevant_prior_context(executor: DefaultTaskExecutor, agent_service, memory_service):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="worker-2", permissions={"read:memory", "write:memory"}, goals=[])
    )
    memory_service.store(
        StoreMemoryCommand(agent_id=agent.agent_id, content="quarterly revenue grew substantially", tags=[])
    )
    task = TaskNode(name="quarterly revenue growth analysis", agent_id=agent.agent_id)
    result = executor.execute(task)

    assert any("revenue" in c for c in result["context_used"])


def test_execute_without_permissions_skips_context_and_storage_gracefully(
    executor: DefaultTaskExecutor, agent_service
):
    agent = agent_service.register_agent(RegisterAgentCommand(name="locked-down", permissions=set(), goals=[]))
    task = TaskNode(name="restricted-task", agent_id=agent.agent_id)

    result = executor.execute(task)  # لا يجب أن يفشل حتى بدون أي صلاحية ذاكرة

    assert result["context_used"] == []
    assert result["task_name"] == "restricted-task"
