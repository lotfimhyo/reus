# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
SecureRemoteExecutor has the same RemoteExecutor contract—send a step and
payload to the node owning a capability—but with one deliberate security
difference.

The original RemoteExecutor sends a plain requests.post to any api_base_url in
PeerDirectory. An actor controlling that address could read a payload or return
forged results. This does not match the rest of the system's mTLS transport
model through TrustStore and SecureNodeClient.

PeerDirectory continues to answer only which node owns a capability_id. The
actual network destination is derived exclusively from TrustStore, the same
transport-trust source used by Raft and discovery. A node absent from TrustStore
is explicitly rejected; no payload is sent through an untrusted channel even if
the node appears in PeerDirectory.

The original RemoteExecutor remains useful only for local development and tests
without physical node networking. It is not used for a real multi-node deployment.
"""
from __future__ import annotations

from typing import Any

from infrastructure.cluster_network.secure_client import SecureNodeClient
from infrastructure.cluster_network.trust_store import TrustStore
from infrastructure.cognitive_core.cluster.peer_directory import PeerDirectory
from infrastructure.cognitive_core.resource.local_executor import HandlerResult

DEFAULT_TIMEOUT_SECONDS = 30.0


class SecureRemoteExecutor:
    def __init__(
        self,
        peer_directory: PeerDirectory,
        trust_store: TrustStore,
        secure_client: SecureNodeClient,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.peer_directory = peer_directory
        self.trust_store = trust_store
        self.secure_client = secure_client
        self.timeout_seconds = timeout_seconds

    def __call__(self, step: Any, payload: dict) -> HandlerResult:
        node_id = self.peer_directory.capability_origin(step.capability_id)
        if node_id is None:
            return HandlerResult(
                success=False, output={}, error=f"No known node owns capability_id={step.capability_id!r}."
            )

        peer = self.trust_store.get_peer(node_id)
        if peer is None:
            # The key difference from RemoteExecutor: a node listed in
            # PeerDirectory but absent from TrustStore is rejected as untrusted
            # at the transport layer, before any payload is sent.
            return HandlerResult(
                success=False,
                output={},
                error=f"Node {node_id!r} is absent from TrustStore; sending was rejected as transport-untrusted.",
            )

        try:
            response = self.secure_client.post_json(
                peer["host"],
                peer["port"],
                "/goals",
                {
                    "description": f"Remote execution of capability {step.name!r}",
                    "required_capability_name": step.name,
                    "payload": payload,
                },
                timeout=self.timeout_seconds,
            )
        except (ConnectionError, OSError, TimeoutError) as exc:
            return HandlerResult(success=False, output={}, error=f"Secure connection to {node_id!r} failed: {exc}")

        if response is None:
            return HandlerResult(success=False, output={}, error=f"Empty response from {node_id!r}.")

        return HandlerResult(
            success=bool(response.get("success", False)),
            output=response.get("output", {}) or {},
            error=response.get("error"),
        )
