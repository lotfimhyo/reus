"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
from unittest.mock import MagicMock

from infrastructure.cluster_network.raft import RaftNode
from infrastructure.cluster_network.raft_cluster_node import RaftClusterNode
from infrastructure.cluster_network.trust_store import TrustStore


def _node() -> RaftClusterNode:
    raft = RaftNode(node_id="transport-local", get_peer_ids=lambda: [], rpc_client=MagicMock())
    return RaftClusterNode(
        node_id="component-local",
        trust_store=TrustStore("/tmp/reus-raft-cluster-node-test-peers.json"),
        capabilities=MagicMock(),
        memory=MagicMock(),
        raft=raft,
        transport_node_id="transport-local",
    )


def test_vote_request_is_rejected_when_claimed_candidate_differs_from_mtls_cn():
    node = _node()

    response = node.handle_request_vote(
        {"term": 1, "candidate_id": "transport-other", "last_log_index": -1, "last_log_term": 0},
        sender_cn="transport-attacker",
    )

    assert response["vote_granted"] is False
    assert response["error"] == "mTLS sender mismatch"
    assert node.raft.current_term == 0


def test_valid_mtls_sender_reaches_raft_vote_handler():
    node = _node()

    response = node.handle_request_vote(
        {"term": 1, "candidate_id": "transport-peer", "last_log_index": -1, "last_log_term": 0},
        sender_cn="transport-peer",
    )

    assert response == {"term": 1, "vote_granted": True}
