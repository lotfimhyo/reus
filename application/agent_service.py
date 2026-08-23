# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""Application-layer use cases independent of FastAPI and HTTP.

Dependencies such as repositories and the event bus are injected so this
service remains testable and replaceable outside a framework.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from domain.entities import Agent, AgentState
from domain.repositories import AgentRepository
from infrastructure.event_bus import Event, EventBus


@dataclass
class RegisterAgentCommand:
    name: str
    permissions: set[str]
    goals: list[str]


class AgentService:
    def __init__(self, repository: AgentRepository, event_bus: EventBus) -> None:
        self._repo = repository
        self._bus = event_bus

    def register_agent(self, cmd: RegisterAgentCommand) -> Agent:
        agent = Agent(name=cmd.name, permissions=cmd.permissions, goals=cmd.goals)
        agent.record_operation(action="register", result="success")
        self._repo.add(agent)
        self._bus.publish(Event(name="agent.created", payload={"agent_id": agent.agent_id, "name": agent.name}))
        return agent

    def get_agent(self, agent_id: str) -> Agent:
        return self._repo.get(agent_id)

    def list_agents(self) -> list[Agent]:
        return self._repo.list_all()

    def change_state(self, agent_id: str, target: AgentState) -> Agent:
        agent = self._repo.get(agent_id)
        agent.transition_to(target)
        self._repo.update(agent)
        self._bus.publish(
            Event(name="agent.state_changed", payload={"agent_id": agent.agent_id, "state": target.value})
        )
        return agent

    def record_call(self, agent_id: str, fn, *args, **kwargs):
        """Execute an operation for an agent while measuring latency and
        recording request-success metrics."""
        agent = self._repo.get(agent_id)
        start = time.perf_counter()
        success = True
        try:
            return fn(*args, **kwargs)
        except Exception:
            success = False
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            agent.record_request(latency_ms=latency_ms, success=success)
            self._repo.update(agent)
