"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Raft RPC adapter over the existing mTLS transport.  Raft peer identifiers
are certificate common names, never hostnames or unverified JSON claims.
"""
from __future__ import annotations

from infrastructure.cluster_network.trust_store import TrustStore


class SecureRaftRpcClient:
    def __init__(self, trust_store: TrustStore, secure_client_factory, timeout_seconds: float = 1.5):
        self._trust_store = trust_store
        self._secure_client_factory = secure_client_factory
        self._timeout_seconds = timeout_seconds

    def _peer(self, transport_node_id: str) -> dict:
        peer = self._trust_store.get_peer_by_transport_id(transport_node_id)
        if peer is None:
            raise ValueError(f"untrusted Raft peer {transport_node_id!r}")
        return peer

    def _client(self):
        # Build from the current trust bundle for each network exchange. This
        # deliberately favors correct behavior immediately after human peer
        # approval over caching a stale TLS context.
        return self._secure_client_factory()

    def request_vote(self, peer_id: str, term: int, candidate_id: str, last_log_index: int, last_log_term: int):
        peer = self._peer(peer_id)
        response = self._client().request_vote(
            peer["host"], peer["port"],
            {
                "term": term,
                "candidate_id": candidate_id,
                "last_log_index": last_log_index,
                "last_log_term": last_log_term,
            },
            timeout=self._timeout_seconds,
        )
        if not isinstance(response, dict):
            raise ConnectionError("empty Raft vote response")
        return int(response["term"]), bool(response["vote_granted"])

    def append_entries(self, peer_id: str, term: int, leader_id: str, prev_log_index: int, prev_log_term: int, entries, leader_commit: int):
        peer = self._peer(peer_id)
        response = self._client().append_entries(
            peer["host"], peer["port"],
            {
                "term": term,
                "leader_id": leader_id,
                "prev_log_index": prev_log_index,
                "prev_log_term": prev_log_term,
                "entries": entries,
                "leader_commit": leader_commit,
            },
            timeout=self._timeout_seconds,
        )
        if not isinstance(response, dict):
            raise ConnectionError("empty Raft append response")
        return int(response["term"]), bool(response["success"])

    def install_snapshot(self, peer_id: str, term: int, leader_id: str, last_included_index: int, last_included_term: int, snapshot_data: dict):
        peer = self._peer(peer_id)
        response = self._client().install_snapshot(
            peer["host"], peer["port"],
            {
                "term": term,
                "leader_id": leader_id,
                "last_included_index": last_included_index,
                "last_included_term": last_included_term,
                "snapshot_data": snapshot_data,
            },
            timeout=max(self._timeout_seconds, 5.0),
        )
        if not isinstance(response, dict):
            raise ConnectionError("empty Raft snapshot response")
        return int(response["term"]), bool(response["success"])
