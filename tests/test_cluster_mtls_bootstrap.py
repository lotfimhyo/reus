"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

End-to-end proof (real sockets, real X.509/mTLS, real Ed25519 signing, real
TelegramService admin gate — nothing mocked except the outbound Telegram
Bot API call itself, exactly like the rest of this project's test suite)
that a brand-new node (B) can:

  1. Discover/contact an existing node (A)'s plain-HTTP bootstrap endpoint.
  2. Have its join request sit PENDING until a human approves it through
     TelegramService (admin_chat_ids-gated, request_approval-gated —
     the exact same double gate as cloud deploy/destroy).
  3. On approval, become mutually mTLS-trusted with A (both TrustStores
     updated) and pull A's real capability + semantic snapshot over
     authenticated mTLS — never over the unauthenticated bootstrap channel.

Run directly (no pytest dependency): `python3 -m unittest tests.test_cluster_mtls_bootstrap -v`
"""
from __future__ import annotations

import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from application.agent_token_service import AgentTokenService
from application.cluster_telegram_commands import ClusterTelegramCommands
from application.orchestrator_service import OrchestratorService
from application.telegram_service import TelegramService
from infrastructure.agent_token_repository import InMemoryAgentTokenRepository
from infrastructure.cluster_network.bootstrap_client import BootstrapClient
from infrastructure.cluster_network.bootstrap_server import BootstrapServer
from infrastructure.cluster_network.cluster_snapshot_node import ClusterSnapshotNode
from infrastructure.cluster_network.identity import NodeIdentity
from infrastructure.cluster_network.join_requests import PendingJoinStore
from infrastructure.cluster_network.secure_client import SecureNodeClient
from infrastructure.cluster_network.secure_server import SecureNodeServer
from infrastructure.cluster_network.trust_store import TrustStore
from infrastructure.cognitive_core.capability.capability_layer import CapabilityLayer
from infrastructure.cognitive_core.capability.descriptor import RiskLevel
from infrastructure.cognitive_core.cluster.mtls_join_client import MTLSJoinClient
from infrastructure.cognitive_core.cluster.peer_directory import PeerDirectory
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog, ComponentIdentity, IdentityRegistry
from infrastructure.cognitive_core.memory.memory_layer import MemoryLayer
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.telegram_link_repository import InMemoryTelegramLinkRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Node:
    """Everything one 'device' needs, built with real crypto/identities."""

    def __init__(self, tmp_root: Path, node_label: str):
        self.dir = tmp_root / node_label
        self.dir.mkdir(parents=True, exist_ok=True)

        self.transport_identity = NodeIdentity(node_label, base_dir=str(self.dir / "transport"))
        self.component_identity = ComponentIdentity.create("node")

        self.audit_log = AppendOnlyAuditLog(str(self.dir / "audit.jsonl"))
        self.identities = IdentityRegistry(persist_path=str(self.dir / "identities.json"))
        self.capabilities = CapabilityLayer(self.audit_log, data_dir=str(self.dir / "capabilities"))
        self.memory = MemoryLayer(self.audit_log, data_dir=str(self.dir / "memory"))
        self.peer_directory = PeerDirectory(data_dir=str(self.dir))
        self.trust_store = TrustStore(peers_file=str(self.dir / "peers.json"))
        self.trust_bundle_path = str(self.dir / "trust_bundle.pem")
        self.trust_store.build_trust_bundle(self.trust_bundle_path, own_cert_pem=self.transport_identity.cert_pem)

        self.mtls_port = _free_port()
        self.bootstrap_port = _free_port()

    def own_identity_payload(self) -> dict:
        return {
            "node_id": self.component_identity.component_id,
            "host": "127.0.0.1",
            "mtls_port": self.mtls_port,
            "cert_pem": self.transport_identity.cert_pem,
            "signing_pubkey_hex": self.transport_identity.signing_public_key_hex,
            "component_public_key_hex": self.component_identity.manifest().public_key_hex,
            "component_created_at": self.component_identity.created_at,
        }

    def secure_client_factory(self, trust_bundle_path: str) -> SecureNodeClient:
        return SecureNodeClient(
            own_cert_path=self.transport_identity.cert_path,
            own_key_path=self.transport_identity.tls_key_path,
            trust_bundle_path=trust_bundle_path,
        )


class TestClusterMTLSBootstrap(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp_root = Path(self._tmp.name)

        self.node_a = _Node(tmp_root, "node-a")
        self.node_b = _Node(tmp_root, "node-b")

        # Node A publishes one real capability and one real fact — this is
        # what B must receive via the post-approval mTLS snapshot pull.
        self.node_a.capabilities.publish(
            component_id="agent-1",
            name="text.uppercase",
            description="Uppercase input text.",
            input_schema={"text": "string"},
            output_schema={"text": "string"},
            estimated_cost=0.0,
            risk_level=RiskLevel.LOW,
        )
        subj = self.node_a.memory.add_entity("text.uppercase", "capability")
        obj = self.node_a.memory.add_entity("reliable", "reliability_class")
        self.node_a.memory.add_fact(subj.id, "has_reliability", obj.id, confidence=1.0)

        # A's real mTLS server, serving the snapshot delegate.
        self.snapshot_node = ClusterSnapshotNode(
            node_id=self.node_a.component_identity.component_id,
            trust_store=self.node_a.trust_store,
            capabilities=self.node_a.capabilities,
            memory=self.node_a.memory,
        )
        self.secure_server = SecureNodeServer(
            node=self.snapshot_node,
            host="127.0.0.1",
            port=self.node_a.mtls_port,
            cert_path=self.node_a.transport_identity.cert_path,
            key_path=self.node_a.transport_identity.tls_key_path,
            trust_bundle_path=self.node_a.trust_bundle_path,
        )
        self.secure_server.start()

        # A's real Telegram admin stack — nothing mocked except the actual
        # outbound Bot API HTTP call (captured via set_delivery_callback,
        # exactly matching every other test in this suite).
        self.admin_chat_id = "admin-chat-1"
        self.sent_messages: list[tuple[str, str]] = []
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

        self.pending_store = PendingJoinStore()
        self.cluster_commands = ClusterTelegramCommands(
            service=self.telegram,
            pending_store=self.pending_store,
            trust_store=self.node_a.trust_store,
            trust_bundle_path=self.node_a.trust_bundle_path,
            admin_chat_ids=frozenset({self.admin_chat_id}),
            event_bus=event_bus,
            on_peer_approved=lambda request: self.secure_server.refresh_trust(self.node_a.trust_bundle_path),
        )

        self.bootstrap_server = BootstrapServer(
            pending_store=self.pending_store,
            own_identity_payload_fn=self.node_a.own_identity_payload,
            host="127.0.0.1",
            port=self.node_a.bootstrap_port,
            on_request_received=self.cluster_commands.notify_new_request,
        )
        self.bootstrap_server.start()
        time.sleep(0.2)  # let both real HTTP(S) servers finish binding

    def tearDown(self):
        self.secure_server.stop()
        self.bootstrap_server.stop()
        self._tmp.cleanup()

    def _human_approves_latest_request(self) -> None:
        """Simulates a real administrator: reads the Telegram notification,
        sends /approve_peer, then confirms with /approve — exactly the two
        real messages a human would type."""
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not self.pending_store.list_pending():
            time.sleep(0.05)
        pending = self.pending_store.list_pending()
        self.assertEqual(len(pending), 1)
        request_id = pending[0].request_id

        reply = self.telegram.handle_incoming_message(self.admin_chat_id, f"/approve_peer {request_id}")
        self.assertEqual(reply, "✅")

        # Extract the approval_id TelegramService generated from the
        # message it actually sent to the admin — proves the real gate ran,
        # not a shortcut around it.
        approval_text = next(text for _, text in self.sent_messages if text.startswith("⚠️"))
        approval_id = approval_text.split("[")[1].split("]")[0]

        reply2 = self.telegram.handle_incoming_message(self.admin_chat_id, f"/approve {approval_id}")
        self.assertEqual(reply2, "✅")
        self.assertTrue(any("Approved:" in text for _, text in self.sent_messages))

    def test_new_node_join_requires_human_approval_and_is_denied_before_it(self):
        join_client = MTLSJoinClient(
            node_identity=self.node_b.component_identity,
            own_identity_payload_fn=self.node_b.own_identity_payload,
            identities=self.node_b.identities,
            capabilities=self.node_b.capabilities,
            memory=self.node_b.memory,
            peer_directory=self.node_b.peer_directory,
            trust_store=self.node_b.trust_store,
            trust_bundle_path=self.node_b.trust_bundle_path,
            secure_client_factory=self.node_b.secure_client_factory,
            bootstrap_client=BootstrapClient(timeout_seconds=5.0, poll_interval_seconds=0.2),
            max_wait_seconds=15.0,
        )

        result_holder: dict = {}

        def run_join():
            result_holder["result"] = join_client.join(
                f"http://127.0.0.1:{self.node_a.bootstrap_port}"
            )

        join_thread = threading.Thread(target=run_join, daemon=True)
        join_thread.start()

        # Before approval: A must not trust B yet.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not self.pending_store.list_pending():
            time.sleep(0.05)
        self.assertIsNone(self.node_a.trust_store.get_peer(self.node_b.component_identity.component_id))

        self._human_approves_latest_request()
        join_thread.join(timeout=15.0)
        self.assertFalse(join_thread.is_alive(), "join() did not complete after human approval")

        result = result_holder["result"]
        self.assertEqual(result.peer_component_id, self.node_a.component_identity.component_id)
        self.assertEqual(result.capabilities_ingested, 1)
        self.assertEqual(result.facts_ingested, 1)

        # Mutual trust now holds on both sides.
        self.assertIsNotNone(self.node_a.trust_store.get_peer(self.node_b.component_identity.component_id))
        self.assertIsNotNone(self.node_b.trust_store.get_peer(self.node_a.component_identity.component_id))

        # B actually received A's real capability via authenticated mTLS.
        discovered_names = [d.name for d in self.node_b.capabilities.discover()]
        self.assertIn("text.uppercase", discovered_names)


if __name__ == "__main__":
    unittest.main()
