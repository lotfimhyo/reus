# Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink
from unittest.mock import MagicMock

from infrastructure.cluster_network.cluster_snapshot_node import fetch_and_apply_snapshot
from infrastructure.cluster_network.membership import VoterConfiguration
from infrastructure.cluster_network.raft import RaftNode, Role
from infrastructure.cluster_network.raft_storage import RaftStorage


class InProcessMembershipRpc:
    def __init__(self):
        self.nodes = {}

    def request_vote(self, peer_id, term, candidate_id, last_log_index, last_log_term):
        return self.nodes[peer_id].handle_request_vote(term, candidate_id, last_log_index, last_log_term)

    def append_entries(self, peer_id, term, leader_id, prev_log_index, prev_log_term, entries, leader_commit):
        return self.nodes[peer_id].handle_append_entries(
            term, leader_id, prev_log_index, prev_log_term, entries, leader_commit
        )

    def install_snapshot(self, peer_id, term, leader_id, last_included_index, last_included_term, snapshot_data, membership=None):
        return self.nodes[peer_id].handle_install_snapshot(
            term, leader_id, last_included_index, last_included_term, snapshot_data, membership
        )


def test_joint_quorum_requires_majority_of_both_voter_sets():
    configuration = VoterConfiguration(frozenset({"a", "b", "c"}), frozenset({"a", "b", "d"}))

    assert configuration.has_quorum({"a", "b"})
    assert not configuration.has_quorum({"a", "c"})
    assert not configuration.has_quorum({"a", "d"})


def test_membership_replacement_commits_joint_then_final_voter_set():
    rpc = InProcessMembershipRpc()
    initial_peers = {
        "a": ["b", "c"],
        "b": ["a", "c"],
        "c": ["a", "b"],
        "d": [],
    }
    nodes = {
        node_id: RaftNode(node_id, get_peer_ids=lambda node_id=node_id: initial_peers[node_id], rpc_client=rpc)
        for node_id in initial_peers
    }
    rpc.nodes = nodes
    assert nodes["d"].install_membership_snapshot({"voters": ["a", "b", "c"]})

    nodes["a"]._start_election()
    assert nodes["a"].role == Role.LEADER
    assert nodes["a"].propose_membership_change(["a", "b", "d"])

    for _ in range(3):
        nodes["a"]._send_heartbeats()

    for node_id in ("a", "b", "c", "d"):
        assert nodes[node_id].status()["voters"] == ["a", "b", "d"]
        assert nodes[node_id].status()["joint_voters"] is None


def test_membership_survives_log_compaction_and_restart(tmp_path):
    storage = RaftStorage(str(tmp_path / "raft.json"))
    node = RaftNode("a", get_peer_ids=lambda: ["b"], rpc_client=MagicMock(), storage=storage)
    node.get_snapshot_data = lambda: {"application": "state"}
    node.handle_append_entries(
        1,
        "b",
        -1,
        0,
        entries=[
            {"term": 1, "command": {"kind": "raft_membership_joint", "old_voters": ["a", "b"], "new_voters": ["a", "c"]}},
            {"term": 1, "command": {"kind": "raft_membership_finalize", "old_voters": ["a", "b"], "new_voters": ["a", "c"]}},
        ],
        leader_commit=1,
    )
    assert node.compact_log()

    restored = RaftNode("a", get_peer_ids=lambda: ["b"], rpc_client=MagicMock(), storage=storage)
    assert restored.status()["voters"] == ["a", "c"]
    assert restored.status()["joint_voters"] is None


def test_authenticated_snapshot_forwards_only_membership_metadata_to_fresh_learner():
    captured: list[dict] = []
    client = MagicMock()
    client.post_json.return_value = {
        "capabilities": [],
        "semantic_facts": [],
        "raft_membership": {"voters": ["a", "b", "c"]},
    }

    result = fetch_and_apply_snapshot(
        client,
        "127.0.0.1",
        8443,
        "component-a",
        MagicMock(),
        MagicMock(),
        MagicMock(),
        on_raft_membership=captured.append,
    )

    assert result == (0, 0)
    assert captured == [{"voters": ["a", "b", "c"]}]
