# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
اختبارات TaskWorker: تتحقق أن المهام تُنفَّذ فعليًا وتلقائيًا (دون استدعاء API يدوي
لكل خطوة) فور جاهزيتها، عبر انتظار نشط (Polling) بمهلة زمنية معقولة، لأن المعالجة
تتم بشكل غير متزامن في خيوط عمّال منفصلة (راجع تعليق التصميم في task_worker.py).
"""
from __future__ import annotations

import time

import pytest

from application.agent_service import AgentService, RegisterAgentCommand
from application.memory_service import MemoryService
from application.orchestrator_service import CreateWorkflowCommand, OrchestratorService
from application.task_worker import TaskWorker
from domain.workflow import TaskSpec
from infrastructure.default_task_executor import DefaultTaskExecutor
from infrastructure.embedding import HashingEmbedder
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.faiss_memory_repository import FaissMemoryRepository
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository

DIM = 128


def _wait_for(predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def agent_repo() -> InMemoryAgentRepository:
    return InMemoryAgentRepository()


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def agent_service(agent_repo, event_bus) -> AgentService:
    return AgentService(repository=agent_repo, event_bus=event_bus)


@pytest.fixture
def memory_service(agent_repo) -> MemoryService:
    return MemoryService(
        memory_repo=FaissMemoryRepository(dimension=DIM),
        agent_repo=agent_repo,
        embedder=HashingEmbedder(dimension=DIM),
    )


@pytest.fixture
def orchestrator(agent_repo, event_bus) -> OrchestratorService:
    return OrchestratorService(workflow_repo=InMemoryWorkflowRepository(), agent_repo=agent_repo, event_bus=event_bus)


@pytest.fixture
def worker(orchestrator, agent_service, memory_service, event_bus):
    executor = DefaultTaskExecutor(agent_service=agent_service, memory_service=memory_service)
    w = TaskWorker(orchestrator=orchestrator, executor=executor, event_bus=event_bus, pool_size=2)
    w.start()
    yield w
    w.stop()


def test_worker_auto_completes_task_for_permitted_agent(worker, orchestrator, agent_service):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="auto-worker", permissions={"read:memory", "write:memory"}, goals=[])
    )
    workflow = orchestrator.create_workflow(
        CreateWorkflowCommand(name="wf", tasks=[TaskSpec(name="analyze", agent_id=agent.agent_id)])
    )

    assert _wait_for(lambda: orchestrator.get_workflow(workflow.workflow_id).is_complete())


def test_worker_fails_task_without_agent(worker, orchestrator):
    workflow = orchestrator.create_workflow(CreateWorkflowCommand(name="wf", tasks=[TaskSpec(name="orphan")]))

    assert _wait_for(lambda: orchestrator.get_workflow(workflow.workflow_id).has_permanent_failure())


def test_worker_cascades_cancellation_when_dependency_fails(worker, orchestrator):
    workflow = orchestrator.create_workflow(
        CreateWorkflowCommand(name="wf", tasks=[TaskSpec(name="root"), TaskSpec(name="child", depends_on=["root"])])
    )

    def child_cancelled() -> bool:
        wf = orchestrator.get_workflow(workflow.workflow_id)
        child = next(t for t in wf.tasks.values() if t.name == "child")
        return child.state.value == "cancelled"

    assert _wait_for(child_cancelled)


def test_worker_processes_multiple_independent_tasks_concurrently(worker, orchestrator, agent_service):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="busy-agent", permissions={"read:memory", "write:memory"}, goals=[])
    )
    workflow = orchestrator.create_workflow(
        CreateWorkflowCommand(
            name="wf",
            tasks=[TaskSpec(name=f"task-{i}", agent_id=agent.agent_id) for i in range(5)],
        )
    )

    assert _wait_for(lambda: orchestrator.get_workflow(workflow.workflow_id).is_complete(), timeout=5.0)
