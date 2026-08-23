"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Seeds one ready-to-use default agent on first startup. In a new system with no
registered agents, Telegram pairing and other agent-dependent features would
otherwise require the operator to open a control plane and create an agent
manually first. This removes only that first manual step; additional agents can
still be registered normally.

The process runs once over the database lifetime rather than creating a duplicate
on every restart. It first confirms that no agents exist. If one or more agents
exist—whether this seed from an earlier run or an operator-created agent—it does
nothing. The absence of this specific seed does not trigger reseeding, because an
operator may have deleted it deliberately.
"""
from __future__ import annotations

import logging

from application.agent_service import AgentService, RegisterAgentCommand
from domain.entities import AgentState

logger = logging.getLogger("reus_veritas.seed_default_agent")

DEFAULT_AGENT_PERMISSIONS = frozenset(
    {"read:memory", "write:memory", "invoke:model", "invoke:tool", "spawn:subagent"}
)


def seed_default_agent(agent_service: AgentService, *, name: str = "default-agent") -> str | None:
    """Return the seeded agent_id when one is created, or None when at least
    one agent already exists and no duplicate seed should be created."""
    if agent_service.list_agents():
        return None

    agent = agent_service.register_agent(
        RegisterAgentCommand(name=name, permissions=set(DEFAULT_AGENT_PERMISSIONS), goals=[])
    )
    # This transition to IDLE is semantically optional, but accurately reflects
    # that this agent is ready to work rather than merely created.
    agent_service.change_state(agent.agent_id, AgentState.IDLE)

    logger.info(
        "default_agent_seeded",
        extra={"event_name": "default_agent_seeded", "payload": {"agent_id": agent.agent_id, "name": name}},
    )
    return agent.agent_id
