# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from application.agent_service import AgentService, RegisterAgentCommand
from domain.entities import AgentState, InvalidStateTransition, PermissionDenied
from domain.repositories import AgentNotFound
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository


@pytest.fixture
def service() -> AgentService:
    return AgentService(repository=InMemoryAgentRepository(), event_bus=InMemoryEventBus())


def test_register_agent_success(service: AgentService):
    agent = service.register_agent(
        RegisterAgentCommand(name="scout-01", permissions={"read:memory"}, goals=["monitor-market"])
    )
    assert agent.state == AgentState.CREATED
    assert agent.name == "scout-01"
    assert len(agent.operation_log) == 1


def test_register_agent_rejects_disallowed_permission(service: AgentService):
    with pytest.raises(PermissionDenied):
        service.register_agent(
            RegisterAgentCommand(name="bad-agent", permissions={"sudo:root"}, goals=[])
        )


def test_get_unknown_agent_raises(service: AgentService):
    with pytest.raises(AgentNotFound):
        service.get_agent("does-not-exist")


def test_list_agents_returns_all_registered(service: AgentService):
    service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    service.register_agent(RegisterAgentCommand(name="b", permissions=set(), goals=[]))
    assert len(service.list_agents()) == 2


def test_valid_state_transition(service: AgentService):
    agent = service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    updated = service.change_state(agent.agent_id, AgentState.IDLE)
    assert updated.state == AgentState.IDLE


def test_invalid_state_transition_rejected(service: AgentService):
    agent = service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    service.change_state(agent.agent_id, AgentState.IDLE)
    service.change_state(agent.agent_id, AgentState.TERMINATED)
    with pytest.raises(InvalidStateTransition):
        service.change_state(agent.agent_id, AgentState.RUNNING)


def test_record_call_tracks_latency_and_errors(service: AgentService):
    agent = service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))

    service.record_call(agent.agent_id, lambda: 1 + 1)
    with pytest.raises(ValueError):
        service.record_call(agent.agent_id, lambda: (_ for _ in ()).throw(ValueError("boom")))

    refreshed = service.get_agent(agent.agent_id)
    assert refreshed.metrics.requests_count == 2
    assert refreshed.metrics.errors_count == 1
