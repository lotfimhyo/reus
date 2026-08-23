# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from application.agent_service import AgentService, RegisterAgentCommand
from application.orchestrator_service import CreateWorkflowCommand, OrchestratorService
from domain.repositories import AgentNotFound
from domain.workflow import TaskSpec, TaskState
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository
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
def orchestrator(agent_repo, event_bus) -> OrchestratorService:
    return OrchestratorService(workflow_repo=InMemoryWorkflowRepository(), agent_repo=agent_repo, event_bus=event_bus)


def test_create_workflow_validates_agent_existence(orchestrator: OrchestratorService):
    with pytest.raises(AgentNotFound):
        orchestrator.create_workflow(
            CreateWorkflowCommand(name="wf", tasks=[TaskSpec(name="t1", agent_id="ghost-agent")])
        )


def test_create_workflow_with_valid_agent(orchestrator: OrchestratorService, agent_service: AgentService):
    agent = agent_service.register_agent(RegisterAgentCommand(name="worker", permissions=set(), goals=[]))
    workflow = orchestrator.create_workflow(
        CreateWorkflowCommand(name="wf", tasks=[TaskSpec(name="t1", agent_id=agent.agent_id)])
    )
    assert len(workflow.tasks) == 1


def test_root_tasks_are_marked_ready_on_creation(orchestrator: OrchestratorService):
    workflow = orchestrator.create_workflow(
        CreateWorkflowCommand(name="wf", tasks=[TaskSpec(name="root"), TaskSpec(name="child", depends_on=["root"])])
    )
    states = {t.name: t.state for t in workflow.tasks.values()}
    assert states["root"] == TaskState.READY
    assert states["child"] == TaskState.PENDING


def test_full_task_lifecycle_completes_workflow(orchestrator: OrchestratorService):
    workflow = orchestrator.create_workflow(CreateWorkflowCommand(name="wf", tasks=[TaskSpec(name="only")]))
    task_id = list(workflow.tasks.keys())[0]

    orchestrator.start_task(workflow.workflow_id, task_id)
    updated = orchestrator.complete_task(workflow.workflow_id, task_id, result={"ok": True})

    assert updated.is_complete() is True


def test_publishes_events_through_lifecycle(orchestrator: OrchestratorService, event_bus: InMemoryEventBus):
    received = []
    event_bus.subscribe("*", lambda e: received.append(e.name))

    workflow = orchestrator.create_workflow(CreateWorkflowCommand(name="wf", tasks=[TaskSpec(name="only")]))
    task_id = list(workflow.tasks.keys())[0]
    orchestrator.start_task(workflow.workflow_id, task_id)
    orchestrator.complete_task(workflow.workflow_id, task_id)

    assert "workflow.created" in received
    assert "task.ready" in received
    assert "task.started" in received
    assert "task.completed" in received
    assert "workflow.completed" in received


def test_fail_task_cascades_and_publishes_failure_events(orchestrator: OrchestratorService, event_bus: InMemoryEventBus):
    received = []
    event_bus.subscribe("*", lambda e: received.append(e.name))

    workflow = orchestrator.create_workflow(
        CreateWorkflowCommand(name="wf", tasks=[TaskSpec(name="root"), TaskSpec(name="child", depends_on=["root"])])
    )
    root_id = next(t.task_id for t in workflow.tasks.values() if t.name == "root")

    orchestrator.start_task(workflow.workflow_id, root_id)
    updated = orchestrator.fail_task(workflow.workflow_id, root_id, error="boom")

    child = next(t for t in updated.tasks.values() if t.name == "child")
    assert child.state == TaskState.CANCELLED
    assert "task.failed" in received
    assert "task.cancelled" in received
    assert "workflow.failed" in received


def test_retry_does_not_cascade_cancel(orchestrator: OrchestratorService):
    workflow = orchestrator.create_workflow(
        CreateWorkflowCommand(name="wf", tasks=[TaskSpec(name="flaky", max_retries=1)])
    )
    task_id = list(workflow.tasks.keys())[0]
    orchestrator.start_task(workflow.workflow_id, task_id)
    updated = orchestrator.fail_task(workflow.workflow_id, task_id, error="temporary")

    task = updated.tasks[task_id]
    assert task.state == TaskState.READY  # PENDING is immediately promoted to READY because it has no dependencies.
    assert task.retry_count == 1
