"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

MTLSJoinClient — replaces the HMAC-cluster-secret `JoinClient`
(cluster_secret.py / join_protocol.py / join_client.py) with the mTLS +
Telegram-gated flow chosen to resolve this project's previously-open
architecture decision. It exposes the exact same public surface the old
`JoinClient` did (`.node_identity`, `.identities`, `.peer_directory`,
`.join(peer_base_url) -> JoinResult`), so `infrastructure.cognitive_core.
cluster.node.ClusterNode` — which only depends on that surface — needs no
changes at all to run on top of it.

What changed underneath: `peer_base_url` is now a bootstrap (plain-HTTP)
base URL, not an already-trusted API. `.join()` submits this device's
certificate, blocks (bounded) until a human approves via Telegram, adds
the now-mutually-trusted peer to TrustStore, then pulls its capability +
semantic snapshot over real mTLS — never over the unauthenticated
bootstrap channel.
"""
from __future__ import annotations

from dataclasses import dataclass

from infrastructure.cluster_network.bootstrap_client import BootstrapClient
from infrastructure.cluster_network.cluster_snapshot_node import fetch_and_apply_snapshot
from infrastructure.cluster_network.trust_store import TrustStore
from infrastructure.cognitive_core.capability.capability_layer import CapabilityLayer
from infrastructure.cognitive_core.cluster.exceptions import ClusterConnectionError, ClusterJoinRejectedError
from infrastructure.cognitive_core.cluster.peer_directory import PeerDirectory
from infrastructure.cognitive_core.identity import ComponentIdentity, IdentityManifest, IdentityRegistry
from infrastructure.cognitive_core.memory.memory_layer import MemoryLayer


@dataclass(frozen=True)
class JoinResult:
    """Kept structurally identical to the old JoinClient's JoinResult so
    ClusterNode's logging/tests need no changes."""

    peer_component_id: str
    capabilities_ingested: int
    facts_ingested: int


class MTLSJoinClient:
    def __init__(
        self,
        node_identity: ComponentIdentity,
        own_identity_payload_fn,
        identities: IdentityRegistry,
        capabilities: CapabilityLayer,
        memory: MemoryLayer,
        peer_directory: PeerDirectory,
        trust_store: TrustStore,
        trust_bundle_path: str,
        secure_client_factory,
        bootstrap_client: BootstrapClient | None = None,
        max_wait_seconds: float = 300.0,
        on_raft_membership=None,
    ):
        """`own_identity_payload_fn()` returns this node's own bootstrap
        payload dict (see bootstrap_server.py) — the same callable a local
        BootstrapServer would use, so both stay in sync automatically.
        `secure_client_factory(trust_bundle_path) -> SecureNodeClient` lets
        the caller supply how a fresh/refreshed mTLS client context is
        built (own cert/key paths are fixed per-node)."""
        self.node_identity = node_identity
        self.own_identity_payload_fn = own_identity_payload_fn
        self.identities = identities
        self.capabilities = capabilities
        self.memory = memory
        self.peer_directory = peer_directory
        self.trust_store = trust_store
        self.trust_bundle_path = trust_bundle_path
        self.secure_client_factory = secure_client_factory
        self.bootstrap = bootstrap_client or BootstrapClient()
        self.max_wait_seconds = max_wait_seconds
        self.on_raft_membership = on_raft_membership

    def join(self, peer_bootstrap_base_url: str) -> JoinResult:
        try:
            request_id = self.bootstrap.request_join(
                peer_bootstrap_base_url, self.own_identity_payload_fn()
            )
            approval = self.bootstrap.poll_until_decided(
                peer_bootstrap_base_url, request_id, max_wait_seconds=self.max_wait_seconds
            )
        except Exception as exc:  # BootstrapRejected/TimedOut/ConnectionError
            from infrastructure.cluster_network.bootstrap_client import BootstrapRejected

            if isinstance(exc, BootstrapRejected):
                raise ClusterJoinRejectedError(str(exc)) from exc
            raise ClusterConnectionError(str(exc)) from exc

        # Mutual trust: the peer approved us; we now trust the peer too.
        self.trust_store.add_peer(
            approval.node_id, approval.host, approval.mtls_port, approval.cert_pem, approval.signing_pubkey_hex
        )
        self.trust_store.save()
        self.trust_store.build_trust_bundle(self.trust_bundle_path)

        self.identities.register(
            IdentityManifest(
                component_id=approval.node_id,
                component_type="node",
                public_key_hex=approval.component_public_key_hex,
                created_at=approval.component_created_at,
            )
        )
        self.peer_directory.register_node(approval.node_id, peer_bootstrap_base_url)

        secure_client = self.secure_client_factory(self.trust_bundle_path)
        capabilities_ingested, facts_ingested = fetch_and_apply_snapshot(
            secure_client,
            approval.host,
            approval.mtls_port,
            approval.node_id,
            self.capabilities,
            self.memory,
            self.peer_directory,
            on_raft_membership=self.on_raft_membership,
        )

        return JoinResult(
            peer_component_id=approval.node_id,
            capabilities_ingested=capabilities_ingested,
            facts_ingested=facts_ingested,
        )
