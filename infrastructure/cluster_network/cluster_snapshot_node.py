"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

ClusterSnapshotNode — the minimal `node` delegate SecureNodeServer needs to
serve GET-like snapshot requests over mTLS (`/cluster/snapshot`), and
`fetch_and_apply_snapshot` — the client-side counterpart that calls it
through `SecureNodeClient` once a peer is in TrustStore, then ingests the
result through the exact same idempotent Memory/Capability facade methods
the old (pre-mTLS) JoinClient used, via
`infrastructure.cognitive_core.cluster.snapshot`.

This intentionally implements ONLY `handle_get_peers` and
`handle_cluster_snapshot` — the two routes this project's bootstrap flow
actually needs. It is not a full Raft/task-execution node; wiring
`/raft/*` and `/submit_task`/`/task_complete` onto a real orchestrator is a
separate, not-yet-composed piece of work (see README "Open items").
"""
from __future__ import annotations

from typing import Any

from infrastructure.cluster_network.secure_client import SecureNodeClient
from infrastructure.cluster_network.trust_store import TrustStore
from infrastructure.cognitive_core.capability.capability_layer import CapabilityLayer
from infrastructure.cognitive_core.cluster.peer_directory import PeerDirectory
from infrastructure.cognitive_core.cluster.snapshot import (
    apply_capability_snapshot,
    apply_semantic_snapshot,
    build_capability_snapshot,
    build_semantic_snapshot,
)
from infrastructure.cognitive_core.memory.memory_layer import MemoryLayer

DEFAULT_TIMEOUT_SECONDS = 15.0


class ClusterSnapshotNode:
    """Server-side delegate: answers `/peers` and `/cluster/snapshot` for
    SecureNodeServer. `node_id` is this device's own component_id."""

    def __init__(
        self,
        node_id: str,
        trust_store: TrustStore,
        capabilities: CapabilityLayer,
        memory: MemoryLayer,
    ):
        self.node_id = node_id
        self.trust_store = trust_store
        self.capabilities = capabilities
        self.memory = memory

    def handle_get_peers(self) -> dict:
        return {"node_id": self.node_id, "peers": list(self.trust_store.all_peers().keys())}

    def handle_cluster_snapshot(self, body: dict, sender_cn: str | None) -> dict:
        # `sender_cn` comes straight from the verified mTLS client
        # certificate (see secure_server.py) — only a peer already present
        # in TrustStore could have completed the handshake at all, so no
        # further authorization check is needed here.
        return {
            "node_id": self.node_id,
            "capabilities": build_capability_snapshot(self.capabilities),
            "semantic_facts": build_semantic_snapshot(self.memory),
        }


def fetch_and_apply_snapshot(
    secure_client: SecureNodeClient,
    peer_host: str,
    peer_port: int,
    peer_node_id: str,
    capabilities: CapabilityLayer,
    memory: MemoryLayer,
    peer_directory: PeerDirectory,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int, int]:
    """Client-side counterpart, called once after a peer has been added to
    TrustStore (mutual trust established). Returns
    (capabilities_ingested, facts_ingested)."""
    response: dict[str, Any] | None = secure_client.post_json(
        peer_host, peer_port, "/cluster/snapshot", {}, timeout=timeout_seconds
    )
    if not response:
        return (0, 0)

    ingested_capabilities = apply_capability_snapshot(capabilities, response.get("capabilities", []))
    for descriptor in ingested_capabilities:
        peer_directory.register_capability_origin(descriptor.capability_id, peer_node_id)

    facts_ingested = apply_semantic_snapshot(memory, response.get("semantic_facts", []))
    return (len(ingested_capabilities), facts_ingested)
