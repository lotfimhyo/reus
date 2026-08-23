"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Tests for seeding a ready default agent at startup, requested directly by the
founder.
"""
from __future__ import annotations

import unittest

from application.agent_service import AgentService, RegisterAgentCommand
from domain.entities import AgentState
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.seed_default_agent import DEFAULT_AGENT_PERMISSIONS, seed_default_agent


class TestSeedDefaultAgent(unittest.TestCase):
    def setUp(self):
        self.service = AgentService(InMemoryAgentRepository(), InMemoryEventBus())

    def test_creates_an_agent_on_a_fresh_system(self):
        agent_id = seed_default_agent(self.service, name="default-agent")

        self.assertIsNotNone(agent_id)
        agent = self.service.get_agent(agent_id)
        self.assertEqual(agent.name, "default-agent")
        self.assertEqual(set(agent.permissions), set(DEFAULT_AGENT_PERMISSIONS))
        self.assertEqual(agent.state, AgentState.IDLE)

    def test_does_not_duplicate_on_a_second_call(self):
        first_id = seed_default_agent(self.service, name="default-agent")
        second_result = seed_default_agent(self.service, name="default-agent")

        self.assertIsNotNone(first_id)
        self.assertIsNone(second_result)
        self.assertEqual(len(self.service.list_agents()), 1)

    def test_does_not_seed_when_a_manually_created_agent_already_exists(self):
        self.service.register_agent(RegisterAgentCommand(name="my-own-agent", permissions=set(), goals=[]))

        result = seed_default_agent(self.service, name="default-agent")

        self.assertIsNone(result)
        self.assertEqual(len(self.service.list_agents()), 1)
        self.assertEqual(self.service.list_agents()[0].name, "my-own-agent")


class TestSeedDefaultAgentStartupWiring(unittest.TestCase):
    def test_a_fresh_app_has_exactly_one_agent_after_startup(self):
        import os

        os.environ["REUS_API_KEY"] = "admin-test"
        import config

        config.get_settings.cache_clear()

        try:
            from fastapi.testclient import TestClient

            from api.main import app

            with TestClient(app) as client:
                response = client.get("/agents", headers={"x-api-key": "admin-test"})
                self.assertEqual(response.status_code, 200)
                agents = response.json()
                self.assertEqual(len(agents), 1)
                self.assertEqual(agents[0]["name"], "default-agent")
        finally:
            os.environ.pop("REUS_API_KEY", None)
            config.get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
