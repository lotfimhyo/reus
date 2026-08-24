"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Run: `python3 -m unittest tests.test_cloud_deploy_node -v`
"""
from __future__ import annotations

import unittest
from typing import List, Optional

from application.agent_token_service import AgentTokenService
from application.cloud_telegram_commands import CloudTelegramCommands
from application.orchestrator_service import OrchestratorService
from application.telegram_service import TelegramService
from infrastructure.agent_token_repository import InMemoryAgentTokenRepository
from infrastructure.cloud.provider_base import CloudConfig, CloudProvider, InstanceInfo
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.telegram_link_repository import InMemoryTelegramLinkRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository


class _FakeCloudProvider(CloudProvider):
    def __init__(self):
        self.created: List[tuple] = []
        self._instances: List[InstanceInfo] = []

    def create_instance(self, name: str, config: CloudConfig) -> InstanceInfo:
        self.created.append((name, config.user_data))
        info = InstanceInfo(
            id=f"id-{len(self.created)}", name=name, provider="fake", region=config.region,
            size=config.size, status="new", monthly_cost_usd=5.0,
        )
        self._instances.append(info)
        return info

    def list_instances(self, config: CloudConfig) -> List[InstanceInfo]:
        return list(self._instances)

    def destroy_instance(self, instance_id: str, config: CloudConfig) -> None:
        self._instances = [i for i in self._instances if i.id != instance_id]

    def estimate_monthly_cost(self, config: CloudConfig) -> float:
        return 5.0


class TestCloudDeployNode(unittest.TestCase):
    def setUp(self):
        self.admin_chat_id = "admin-chat-1"
        self.sent_messages: list = []
        event_bus = InMemoryEventBus()
        agent_repo = InMemoryAgentRepository()
        token_service = AgentTokenService(token_repo=InMemoryAgentTokenRepository(), agent_repo=agent_repo)
        orchestrator = OrchestratorService(
            workflow_repo=InMemoryWorkflowRepository(), agent_repo=agent_repo, event_bus=event_bus
        )
        self.telegram = TelegramService(
            link_repo=InMemoryTelegramLinkRepository(),
            token_service=token_service,
            orchestrator=orchestrator,
            event_bus=event_bus,
            admin_chat_ids=frozenset({self.admin_chat_id}),
        )
        self.telegram.set_delivery_callback(lambda chat_id, text: self.sent_messages.append((chat_id, text)))
        self.telegram.start()

        self.fake_provider = _FakeCloudProvider()
        self.seed_url: Optional[str] = None
        self.cloud_commands = CloudTelegramCommands(
            service=self.telegram,
            provider_factory=lambda name: self.fake_provider,
            event_bus=event_bus,
            seed_bootstrap_url_provider=lambda: self.seed_url,
            token_resolver=lambda _provider: "test-provider-token",
        )

    def _configure_cloud(self, with_source_fetch_cmd: bool = True) -> None:
        cmd = (
            "/configure_cloud provider=digitalocean region=nyc3 "
            "size=s-1vcpu-1gb max_instances=2 budget_cap=20"
        )
        if with_source_fetch_cmd:
            cmd += ' source_fetch_cmd="git clone https://example.com/reus.git /opt/reus"'
        reply = self.telegram.handle_incoming_message(self.admin_chat_id, cmd)
        self.assertEqual(reply, "✅")

    def test_deploy_rejects_unknown_role(self):
        self._configure_cloud()
        reply = self.telegram.handle_incoming_message(self.admin_chat_id, "/deploy_node no-such-role")
        self.assertEqual(reply, "✅")
        self.assertTrue(any("Available roles" in text for _, text in self.sent_messages))
        self.assertEqual(len(self.fake_provider.created), 0)

    def test_deploy_refuses_without_source_fetch_cmd_configured(self):
        self._configure_cloud(with_source_fetch_cmd=False)
        # The configuration itself is rejected without source_fetch_cmd; no
        # partial configuration is retained.
        self.assertTrue(any("source_fetch_cmd" in text for _, text in self.sent_messages))
        reply = self.telegram.handle_incoming_message(self.admin_chat_id, "/deploy_node text-node")
        self.assertEqual(reply, "✅")
        self.assertTrue(any("Cloud is not configured yet" in text for _, text in self.sent_messages))
        self.assertEqual(len(self.fake_provider.created), 0)

    def test_full_deploy_flow_generates_real_cloud_init_and_creates_instance(self):
        self._configure_cloud()
        self.seed_url = "http://10.0.0.1:8080"

        reply1 = self.telegram.handle_incoming_message(self.admin_chat_id, "/deploy_node text-node my-text-node")
        self.assertEqual(reply1, "✅")

        approval_text = next(text for _, text in self.sent_messages if text.startswith("⚠️"))
        self.assertIn("Role: text-node", approval_text)
        self.assertIn("http://10.0.0.1:8080", approval_text)
        approval_id = approval_text.split("[")[1].split("]")[0]

        reply2 = self.telegram.handle_incoming_message(self.admin_chat_id, f"/approve {approval_id}")
        self.assertEqual(reply2, "✅")

        self.assertEqual(len(self.fake_provider.created), 1)
        name, user_data = self.fake_provider.created[0]
        self.assertEqual(name, "my-text-node")
        self.assertIn("--role text-node", user_data)
        self.assertIn("--seed-url http://10.0.0.1:8080", user_data)
        self.assertIn("git clone https://example.com/reus.git /opt/reus", user_data)
        self.assertIn("systemctl enable --now reus-node.service", user_data)

        self.assertTrue(any("Deployed:" in text and "text-node" in text for _, text in self.sent_messages))

    def test_deploy_without_seed_url_provider_creates_standalone_node(self):
        self._configure_cloud()
        self.seed_url = None

        self.telegram.handle_incoming_message(self.admin_chat_id, "/deploy_node cipher-node")
        approval_text = next(text for _, text in self.sent_messages if text.startswith("⚠️"))
        self.assertIn("independent node", approval_text)
        approval_id = approval_text.split("[")[1].split("]")[0]
        self.telegram.handle_incoming_message(self.admin_chat_id, f"/approve {approval_id}")

        _, user_data = self.fake_provider.created[0]
        self.assertNotIn("--seed-url", user_data)

    def test_user_data_reset_between_deployments_of_different_roles(self):
        self._configure_cloud()

        self.telegram.handle_incoming_message(self.admin_chat_id, "/deploy_node text-node n1")
        approval_text_1 = next(t for _, t in self.sent_messages if t.startswith("⚠️"))
        approval_id_1 = approval_text_1.split("[")[1].split("]")[0]
        self.telegram.handle_incoming_message(self.admin_chat_id, f"/approve {approval_id_1}")

        self.telegram.handle_incoming_message(self.admin_chat_id, "/deploy_node numeric-node n2")
        approval_text_2 = [t for _, t in self.sent_messages if t.startswith("⚠️")][-1]
        approval_id_2 = approval_text_2.split("[")[1].split("]")[0]
        self.telegram.handle_incoming_message(self.admin_chat_id, f"/approve {approval_id_2}")

        self.assertEqual(len(self.fake_provider.created), 2)
        _, user_data_1 = self.fake_provider.created[0]
        _, user_data_2 = self.fake_provider.created[1]
        self.assertIn("--role text-node", user_data_1)
        self.assertIn("--role numeric-node", user_data_2)
        self.assertNotIn("numeric-node", user_data_1)
        self.assertNotIn("text-node", user_data_2)


if __name__ == "__main__":
    unittest.main()
