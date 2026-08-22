# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from application.agent_service import AgentService, RegisterAgentCommand
from application.observability_service import ObservabilityService
from application.orchestrator_service import CreateWorkflowCommand, OrchestratorService
from domain.entities import AgentState
from domain.workflow import TaskSpec
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.event_log_repository import InMemoryEventLogRepository
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def agent_repo() -> InMemoryAgentRepository:
    return InMemoryAgentRepository()


@pytest.fixture
def workflow_repo() -> InMemoryWorkflowRepository:
    return InMemoryWorkflowRepository()


@pytest.fixture
def agent_service(agent_repo, event_bus) -> AgentService:
    return AgentService(repository=agent_repo, event_bus=event_bus)


@pytest.fixture
def orchestrator(agent_repo, workflow_repo, event_bus) -> OrchestratorService:
    return OrchestratorService(workflow_repo=workflow_repo, agent_repo=agent_repo, event_bus=event_bus)


@pytest.fixture
def observability(agent_repo, workflow_repo, event_bus) -> ObservabilityService:
    service = ObservabilityService(
        event_log_repo=InMemoryEventLogRepository(),
        agent_repo=agent_repo,
        workflow_repo=workflow_repo,
        event_bus=event_bus,
    )
    service.start()
    return service


def test_summary_with_no_data_is_all_zeros(observability: ObservabilityService):
    summary = observability.get_summary()
    assert summary.agents_total == 0
    assert summary.workflows_total == 0
    assert summary.tasks_total == 0


def test_records_agent_creation_event_automatically(
    observability: ObservabilityService, agent_service: AgentService
):
    agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))

    events = observability.get_recent_events()
    names = [e.name for e in events]
    assert "agent.created" in names


def test_summary_counts_agents_by_state(observability: ObservabilityService, agent_service: AgentService):
    a1 = agent_service.register_agent(RegisterAgentCommand(name="a1", permissions=set(), goals=[]))
    agent_service.register_agent(RegisterAgentCommand(name="a2", permissions=set(), goals=[]))
    agent_service.change_state(a1.agent_id, AgentState.IDLE)

    summary = observability.get_summary()

    assert summary.agents_total == 2
    assert summary.agents_by_state["idle"] == 1
    assert summary.agents_by_state["created"] == 1


def test_summary_counts_workflow_and_task_states(
    observability: ObservabilityService, orchestrator: OrchestratorService
):
    workflow = orchestrator.create_workflow(
        CreateWorkflowCommand(name="wf", tasks=[TaskSpec(name="a"), TaskSpec(name="b", depends_on=["a"])])
    )
    a_id = next(t.task_id for t in workflow.tasks.values() if t.name == "a")
    orchestrator.start_task(workflow.workflow_id, a_id)
    orchestrator.complete_task(workflow.workflow_id, a_id)

    summary = observability.get_summary()

    assert summary.workflows_total == 1
    assert summary.workflows_in_progress == 1
    assert summary.tasks_total == 2
    assert summary.tasks_by_state["completed"] == 1
    assert summary.tasks_by_state["ready"] == 1


def test_get_recent_events_filters_by_name(observability: ObservabilityService, agent_service: AgentService):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    agent_service.change_state(agent.agent_id, AgentState.IDLE)

    filtered = observability.get_recent_events(name_filter="agent.state_changed")

    assert len(filtered) == 1
    assert filtered[0].name == "agent.state_changed"


def test_recent_events_ordered_most_recent_first(observability: ObservabilityService, agent_service: AgentService):
    agent_service.register_agent(RegisterAgentCommand(name="first", permissions=set(), goals=[]))
    agent_service.register_agent(RegisterAgentCommand(name="second", permissions=set(), goals=[]))

    events = observability.get_recent_events()

    assert events[0].payload.get("name") == "second"
    assert events[-1].payload.get("name") == "first"
