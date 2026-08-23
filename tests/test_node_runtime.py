"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Verifies that `infrastructure/node_runtime.py` (the same functions invoked by
`scripts/run_node.py`) composes a node with all skills defined in
`node_roles.py`. It also verifies that two nodes composed through that path can
join one another using the local mTLS and Telegram-approval test flow; it does
not perform an external Telegram provider verification.

Run: `python3 -m unittest tests.test_node_runtime -v`
"""
from __future__ import annotations

import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from application.agent_token_service import AgentTokenService
from application.cluster_telegram_commands import ClusterTelegramCommands
from application.orchestrator_service import CreateWorkflowCommand, OrchestratorService
from application.telegram_service import TelegramService
from domain.workflow import TaskSpec
from infrastructure.agent_token_repository import InMemoryAgentTokenRepository
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.node_runtime import compose_node, join_cluster, start_node, stop_node
from infrastructure.telegram_link_repository import InMemoryTelegramLinkRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestNodeRuntime(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_compose_node_rejects_unknown_role(self):
        with self.assertRaises(ValueError):
            compose_node(role_id="no-such-role", data_dir=str(Path(self._tmp.name) / "n"))

    def test_compose_node_builds_and_binds_all_role_skills(self):
        composed = compose_node(
            role_id="numeric-node",
            data_dir=str(Path(self._tmp.name) / "n1"),
            mtls_port=_free_port(),
            bootstrap_port=_free_port(),
        )
        from infrastructure.node_roles import NODE_ROLES

        expected = len(NODE_ROLES["numeric-node"].specs)
        self.assertEqual(composed.skills_bound, expected)

        discovered = [d.name for d in composed.capabilities.discover()]
        self.assertIn("numeric.is_prime", discovered)
        self.assertIn("numeric.factorial", discovered)

        descriptor = next(d for d in composed.capabilities.discover() if d.name == "numeric.is_prime")

        class _Step:
            pass

        step = _Step()
        step.capability_id = descriptor.capability_id
        result = composed.executor(step, {"input": 17})
        self.assertTrue(result.success)
        self.assertTrue(result.output)

    def test_component_and_transport_identity_are_stable_when_recomposed(self):
        data_dir = str(Path(self._tmp.name) / "stable-node")
        first = compose_node("text-node", data_dir, mtls_port=_free_port(), bootstrap_port=_free_port())
        second = compose_node("text-node", data_dir, mtls_port=_free_port(), bootstrap_port=_free_port())

        self.assertEqual(first.component_identity.component_id, second.component_identity.component_id)
        self.assertEqual(first.transport_node_id, second.transport_node_id)

    def test_composed_node_builds_task_worker_with_its_raft_lease_coordinator(self):
        composed = compose_node(
            role_id="numeric-node",
            data_dir=str(Path(self._tmp.name) / "worker-node"),
            mtls_port=_free_port(),
            bootstrap_port=_free_port(),
        )

        worker = composed.build_task_worker(MagicMock(), MagicMock(), MagicMock(), pool_size=1)

        self.assertIs(worker._lease_coordinator, composed.task_coordinator)

    def test_started_composed_node_runs_workflow_through_committed_raft_lease(self):
        composed = compose_node(
            role_id="numeric-node",
            data_dir=str(Path(self._tmp.name) / "runtime-worker-node"),
            mtls_port=_free_port(),
            bootstrap_port=_free_port(),
        )
        event_bus = InMemoryEventBus()
        orchestrator = OrchestratorService(
            workflow_repo=InMemoryWorkflowRepository(),
            agent_repo=InMemoryAgentRepository(),
            event_bus=event_bus,
        )
        executor = MagicMock()
        executor.execute.return_value = {"result": "cluster-ok"}
        worker = composed.build_task_worker(orchestrator, executor, event_bus, pool_size=1)

        start_node(composed)
        try:
            composed.raft._start_election()
            worker.start()
            workflow = orchestrator.create_workflow(
                CreateWorkflowCommand(name="cluster-workflow", tasks=[TaskSpec(name="cluster-task")])
            )

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and not orchestrator.get_workflow(workflow.workflow_id).is_complete():
                time.sleep(0.02)

            self.assertTrue(orchestrator.get_workflow(workflow.workflow_id).is_complete())
            task_id = next(iter(workflow.tasks))
            self.assertEqual(composed.raft_cluster.task_state._tasks[f"{workflow.workflow_id}:{task_id}"]["status"], "completed")
            executor.execute.assert_called_once()
        finally:
            worker.stop()
            stop_node(composed)

    def test_two_production_composed_nodes_join_via_real_mtls_and_telegram_approval(self):
        tmp_root = Path(self._tmp.name)

        node_a = compose_node(
            role_id="text-node",
            data_dir=str(tmp_root / "a"),
            mtls_port=_free_port(),
            bootstrap_port=_free_port(),
            node_label="node-a",
        )
        node_b = compose_node(
            role_id="cipher-node",
            data_dir=str(tmp_root / "b"),
            mtls_port=_free_port(),
            bootstrap_port=_free_port(),
            node_label="node-b",
        )

        start_node(node_a)
        start_node(node_b)

        admin_chat_id = "admin-chat-1"
        sent_messages: list = []
        event_bus = InMemoryEventBus()
        agent_repo = InMemoryAgentRepository()
        token_service = AgentTokenService(token_repo=InMemoryAgentTokenRepository(), agent_repo=agent_repo)
        orchestrator = OrchestratorService(
            workflow_repo=InMemoryWorkflowRepository(), agent_repo=agent_repo, event_bus=event_bus
        )
        telegram = TelegramService(
            link_repo=InMemoryTelegramLinkRepository(),
            token_service=token_service,
            orchestrator=orchestrator,
            event_bus=event_bus,
            admin_chat_ids=frozenset({admin_chat_id}),
        )
        telegram.set_delivery_callback(lambda chat_id, text: sent_messages.append((chat_id, text)))
        telegram.start()

        cluster_commands = ClusterTelegramCommands(
            service=telegram,
            pending_store=node_a.pending_join_store,
            trust_store=node_a.trust_store,
            trust_bundle_path=node_a.trust_bundle_path,
            admin_chat_ids=frozenset({admin_chat_id}),
            event_bus=event_bus,
            on_peer_approved=lambda request: node_a.secure_server.refresh_trust(node_a.trust_bundle_path),
        )
        node_a.bootstrap_server.on_request_received = cluster_commands.notify_new_request

        result_holder: dict = {}

        def run_join():
            result_holder["result"] = join_cluster(
                node_b, f"http://127.0.0.1:{node_a.bootstrap_port}", max_wait_seconds=15.0
            )

        join_thread = threading.Thread(target=run_join, daemon=True)
        join_thread.start()

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not node_a.pending_join_store.list_pending():
            time.sleep(0.05)
        pending = node_a.pending_join_store.list_pending()
        self.assertEqual(len(pending), 1)
        request_id = pending[0].request_id

        reply1 = telegram.handle_incoming_message(admin_chat_id, f"/approve_peer {request_id}")
        self.assertEqual(reply1, "✅")
        approval_text = next(text for _, text in sent_messages if text.startswith("⚠️"))
        approval_id = approval_text.split("[")[1].split("]")[0]
        reply2 = telegram.handle_incoming_message(admin_chat_id, f"/approve {approval_id}")
        self.assertEqual(reply2, "✅")

        join_thread.join(timeout=15.0)
        self.assertFalse(join_thread.is_alive())

        result = result_holder["result"]
        self.assertEqual(result.peer_component_id, node_a.component_identity.component_id)
        self.assertGreater(result.capabilities_ingested, 0)

        discovered_b = [d.name for d in node_b.capabilities.discover()]
        self.assertIn("text.uppercase", discovered_b)

        election_deadline = time.monotonic() + 8.0
        while time.monotonic() < election_deadline:
            statuses = (node_a.raft.status(), node_b.raft.status())
            leaders = [status for status in statuses if status["role"] == "leader"]
            if len(leaders) == 1 and all(status["leader_id"] == leaders[0]["node_id"] for status in statuses):
                break
            time.sleep(0.05)
        statuses = (node_a.raft.status(), node_b.raft.status())
        leaders = [status for status in statuses if status["role"] == "leader"]
        self.assertEqual(len(leaders), 1)
        self.assertTrue(all(status["leader_id"] == leaders[0]["node_id"] for status in statuses))

        stop_node(node_a)
        stop_node(node_b)


if __name__ == "__main__":
    unittest.main()
