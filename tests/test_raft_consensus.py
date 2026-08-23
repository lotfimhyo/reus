"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

First direct tests for RaftStorage and RaftNode (infrastructure/cluster_network/
raft.py and raft_storage.py). They cover the Raft safety properties documented
by the code; this is not an exhaustive protocol implementation test.

- Persistence across a restart: construct a node, alter its state, construct a
  new node from the same storage file, and verify restored state.
- The one-vote-per-term rule, which is core to Raft election safety.
- Rejection of stale-term RPCs.
- Log replication and replacement of conflicting entries.
- Majority commit and on_commit invocation.
- Log compaction through a snapshot and snapshot restoration.
- Winning an election with a majority and stepping down after a higher term.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from infrastructure.cluster_network.raft import RaftNode, Role
from infrastructure.cluster_network.raft_storage import RaftStorage


class TestRaftStorage(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.storage = RaftStorage(f"{self.tmp_dir}/raft_state.json")

    def test_load_returns_none_for_brand_new_node(self):
        self.assertIsNone(self.storage.load())

    def test_save_then_load_roundtrips_exactly(self):
        log = [{"term": 1, "index": 0, "command": {"op": "noop"}}]
        self.storage.save(current_term=3, voted_for="node-b", log_entries=log)
        term, voted_for, loaded_log = self.storage.load()
        self.assertEqual(term, 3)
        self.assertEqual(voted_for, "node-b")
        self.assertEqual(loaded_log, log)

    def test_snapshot_save_then_load_roundtrips_exactly(self):
        self.assertIsNone(self.storage.load_snapshot())
        self.storage.save_snapshot(5, 2, {"tasks": ["a", "b"]})
        index, term, data = self.storage.load_snapshot()
        self.assertEqual(index, 5)
        self.assertEqual(term, 2)
        self.assertEqual(data, {"tasks": ["a", "b"]})

    def test_second_save_does_not_leave_a_stale_tmp_file_behind(self):
        """Verify that atomic write-then-rename leaves no stale .tmp files,
        providing indirect evidence that the rename path completes."""
        import os

        self.storage.save(1, None, [])
        self.storage.save(2, "x", [{"term": 1, "index": 0, "command": {}}])
        self.assertFalse(os.path.exists(f"{self.storage._path}.tmp"))


class TestRaftNodePersistenceAcrossRestart(unittest.TestCase):
    """Verify that a fresh node constructed from the same storage file restores
    accepted votes, terms, and log entries, which is a core Raft safety property."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.storage_path = f"{self.tmp_dir}/raft_state.json"

    def _new_node(self, node_id="node-a"):
        return RaftNode(
            node_id=node_id,
            get_peer_ids=lambda: [],
            rpc_client=MagicMock(),
            storage=RaftStorage(self.storage_path),
        )

    def test_vote_and_term_survive_a_real_restart(self):
        node = self._new_node()
        term, granted = node.handle_request_vote(
            term=5, candidate_id="node-b", last_log_index=-1, last_log_term=0
        )
        self.assertTrue(granted)
        self.assertEqual(term, 5)

        # A new node object models a restart after failure rather than reuse.
        restarted = self._new_node()
        self.assertEqual(restarted.current_term, 5)
        self.assertEqual(restarted.voted_for, "node-b")

    def test_replicated_log_entries_survive_a_real_restart(self):
        node = self._new_node()
        term, ok = node.handle_append_entries(
            term=1, leader_id="leader-1", prev_log_index=-1, prev_log_term=0,
            entries=[{"term": 1, "command": {"op": "assign_task", "task": "t1"}}],
            leader_commit=-1,
        )
        self.assertTrue(ok)

        restarted = self._new_node()
        self.assertEqual(len(restarted.log), 1)
        self.assertEqual(restarted.log[0].command, {"op": "assign_task", "task": "t1"})
        self.assertEqual(restarted.current_term, 1)

    def test_commit_position_survives_restart_and_can_restore_state_machine(self):
        node = self._new_node()
        committed_before_restart = []
        node.on_commit = lambda entry: committed_before_restart.append(entry.command)
        node.handle_append_entries(
            term=1,
            leader_id="leader-1",
            prev_log_index=-1,
            prev_log_term=0,
            entries=[{"term": 1, "command": {"op": "governed_assignment"}}],
            leader_commit=0,
        )
        self.assertEqual(node.commit_index, 0)
        self.assertEqual(committed_before_restart, [{"op": "governed_assignment"}])

        restarted = self._new_node()
        restored = []
        restarted.on_commit = lambda entry: restored.append(entry.command)
        restarted.replay_committed()

        self.assertEqual(restarted.commit_index, 0)
        self.assertEqual(restored, [{"op": "governed_assignment"}])


class TestRaftNodeVoteSafety(unittest.TestCase):
    def _node(self):
        return RaftNode(node_id="n1", get_peer_ids=lambda: [], rpc_client=MagicMock())

    def test_grants_vote_when_log_up_to_date_and_not_yet_voted(self):
        node = self._node()
        term, granted = node.handle_request_vote(1, "candidate-a", -1, 0)
        self.assertTrue(granted)
        self.assertEqual(node.voted_for, "candidate-a")

    def test_rejects_stale_term(self):
        node = self._node()
        node.handle_request_vote(5, "candidate-a", -1, 0)  # bumps current_term to 5
        term, granted = node.handle_request_vote(3, "candidate-b", -1, 0)
        self.assertFalse(granted)
        self.assertEqual(term, 5)

    def test_refuses_second_vote_for_different_candidate_same_term(self):
        """Raft election safety allows only one vote per term; otherwise two
        leaders could be elected in one term and violate consistency."""
        node = self._node()
        _, first = node.handle_request_vote(1, "candidate-a", -1, 0)
        _, second = node.handle_request_vote(1, "candidate-b", -1, 0)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(node.voted_for, "candidate-a")

    def test_regrants_same_vote_idempotently_for_same_candidate_same_term(self):
        node = self._node()
        node.handle_request_vote(1, "candidate-a", -1, 0)
        _, granted_again = node.handle_request_vote(1, "candidate-a", -1, 0)
        self.assertTrue(granted_again)

    def test_steps_down_and_resets_vote_on_seeing_higher_term(self):
        node = self._node()
        node.handle_request_vote(1, "candidate-a", -1, 0)
        node.handle_request_vote(9, "candidate-b", -1, 0)
        self.assertEqual(node.current_term, 9)
        self.assertEqual(node.voted_for, "candidate-b")


class TestRaftNodeLogReplication(unittest.TestCase):
    def _node(self):
        return RaftNode(node_id="follower-1", get_peer_ids=lambda: [], rpc_client=MagicMock())

    def test_rejects_append_entries_with_stale_term(self):
        node = self._node()
        node.handle_append_entries(5, "leader-1", -1, 0, [], -1)  # bumps term to 5
        term, ok = node.handle_append_entries(3, "leader-2", -1, 0, [], -1)
        self.assertFalse(ok)
        self.assertEqual(term, 5)

    def test_heartbeat_with_no_entries_still_updates_leader_and_deadline(self):
        node = self._node()
        term, ok = node.handle_append_entries(1, "leader-1", -1, 0, [], -1)
        self.assertTrue(ok)
        self.assertEqual(node.leader_id, "leader-1")
        self.assertEqual(node.role, Role.FOLLOWER)

    def test_conflicting_entry_truncates_and_replaces_the_log(self):
        node = self._node()
        node.handle_append_entries(1, "leader-1", -1, 0, [{"term": 1, "command": {"v": "old"}}], -1)
        # Same index with a different term is a conflict; replace, do not append.
        node.handle_append_entries(2, "leader-1", -1, 0, [{"term": 2, "command": {"v": "new"}}], -1)
        self.assertEqual(len(node.log), 1)
        self.assertEqual(node.log[0].command, {"v": "new"})

    def test_leader_commit_advances_local_commit_index_and_fires_on_commit(self):
        node = self._node()
        committed = []
        node.on_commit = lambda entry: committed.append(entry.command)

        node.handle_append_entries(
            1, "leader-1", -1, 0,
            entries=[{"term": 1, "command": {"v": "a"}}, {"term": 1, "command": {"v": "b"}}],
            leader_commit=1,
        )
        self.assertEqual(committed, [{"v": "a"}, {"v": "b"}])
        self.assertEqual(node.commit_index, 1)


class TestRaftNodeLogCompaction(unittest.TestCase):
    def test_compact_log_persists_snapshot_and_shortens_log(self):
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        storage = RaftStorage(f"{tmp_dir}/state.json")
        node = RaftNode(
            node_id="n1", get_peer_ids=lambda: [], rpc_client=MagicMock(), storage=storage
        )
        node.get_snapshot_data = lambda: {"state": "snapshotted"}
        node.handle_append_entries(
            1, "leader-1", -1, 0,
            entries=[{"term": 1, "command": {"v": "a"}}, {"term": 1, "command": {"v": "b"}}],
            leader_commit=1,
        )
        self.assertEqual(len(node.log), 2)

        compacted = node.compact_log(upto_index=0)
        self.assertTrue(compacted)
        self.assertEqual(len(node.log), 1)  # only index 1 remains uncompacted

        loaded_snapshot = storage.load_snapshot()
        self.assertIsNotNone(loaded_snapshot)
        self.assertEqual(loaded_snapshot[2], {"state": "snapshotted"})

    def test_compact_log_returns_false_when_nothing_new_to_compact(self):
        node = RaftNode(node_id="n1", get_peer_ids=lambda: [], rpc_client=MagicMock())
        self.assertFalse(node.compact_log())  # commit_index starts at -1, nothing committed yet


class TestRaftNodeElection(unittest.TestCase):
    def test_wins_election_with_majority_of_votes(self):
        rpc = MagicMock()
        rpc.request_vote.return_value = (1, True)  # every peer grants the vote
        node = RaftNode(node_id="n1", get_peer_ids=lambda: ["n2", "n3"], rpc_client=rpc)

        node._start_election()

        self.assertEqual(node.role, Role.LEADER)
        self.assertEqual(node.leader_id, "n1")

    def test_steps_down_if_a_peer_reports_a_higher_term(self):
        rpc = MagicMock()
        rpc.request_vote.return_value = (99, False)  # peer is on a much later term
        node = RaftNode(node_id="n1", get_peer_ids=lambda: ["n2"], rpc_client=rpc)

        node._start_election()

        self.assertEqual(node.role, Role.FOLLOWER)
        self.assertEqual(node.current_term, 99)

    def test_loses_election_without_majority(self):
        rpc = MagicMock()
        rpc.request_vote.return_value = (1, False)  # every peer refuses
        node = RaftNode(node_id="n1", get_peer_ids=lambda: ["n2", "n3"], rpc_client=rpc)

        node._start_election()

        self.assertNotEqual(node.role, Role.LEADER)


class _InProcessRaftRpc:
    """Partitionable in-process test network that simulates connectivity loss
    without fabricating RPC results."""

    def __init__(self):
        self.nodes = {}
        self.unavailable = set()

    def _node(self, peer_id):
        if peer_id in self.unavailable:
            raise ConnectionError(f"peer {peer_id} is unavailable")
        return self.nodes[peer_id]

    def request_vote(self, peer_id, term, candidate_id, last_log_index, last_log_term):
        return self._node(peer_id).handle_request_vote(term, candidate_id, last_log_index, last_log_term)

    def append_entries(self, peer_id, term, leader_id, prev_log_index, prev_log_term, entries, leader_commit):
        return self._node(peer_id).handle_append_entries(
            term, leader_id, prev_log_index, prev_log_term, entries, leader_commit
        )

    def install_snapshot(self, peer_id, term, leader_id, last_included_index, last_included_term, snapshot_data):
        return self._node(peer_id).handle_install_snapshot(
            term, leader_id, last_included_index, last_included_term, snapshot_data
        )


class TestRaftLeaderFailureRecovery(unittest.TestCase):
    def test_majority_elects_replacement_and_commits_after_old_leader_isolated(self):
        rpc = _InProcessRaftRpc()
        peers = {"a": ["b", "c"], "b": ["a", "c"], "c": ["a", "b"]}
        nodes = {
            node_id: RaftNode(node_id, get_peer_ids=lambda node_id=node_id: peers[node_id], rpc_client=rpc)
            for node_id in peers
        }
        rpc.nodes = nodes

        nodes["a"]._start_election()
        self.assertEqual(nodes["a"].role, Role.LEADER)

        # Model a leader failure or network isolation; B and C retain 2/3 majority.
        rpc.unavailable.add("a")
        nodes["b"]._start_election()
        self.assertEqual(nodes["b"].role, Role.LEADER)
        self.assertEqual(nodes["b"].current_term, 2)

        self.assertTrue(nodes["b"].propose({"op": "reassign_after_failure", "task_id": "task-1"}))
        nodes["b"]._send_heartbeats()
        # The first round replicates then commits after a majority ACK.
        # The next round carries leader_commit to the follower, as Raft requires.
        nodes["b"]._send_heartbeats()

        self.assertEqual(nodes["b"].commit_index, 0)
        self.assertEqual(nodes["c"].commit_index, 0)
        self.assertEqual(nodes["c"].leader_id, "b")
        self.assertEqual(nodes["a"].commit_index, -1)

    def test_expired_lease_is_requeued_and_reassigned_by_replacement_leader(self):
        """End-to-end work-state test, not only an election test: a leader fails
        after a committed lease, then a majority elects a replacement that
        requeues and reassigns the expired task. The log carries no raw payload
        or memory content."""
        from infrastructure.cluster_network.raft_cluster_node import RaftClusterNode
        from infrastructure.cluster_network.trust_store import TrustStore

        rpc = _InProcessRaftRpc()
        peers = {"a": ["b", "c"], "b": ["a", "c"], "c": ["a", "b"]}
        rafts = {node_id: RaftNode(node_id, get_peer_ids=lambda node_id=node_id: peers[node_id], rpc_client=rpc) for node_id in peers}
        rpc.nodes = rafts
        clusters = {
            node_id: RaftClusterNode(
                node_id=f"component-{node_id}", transport_node_id=node_id,
                trust_store=TrustStore(f"/tmp/reus-lease-{node_id}-peers.json"),
                capabilities=MagicMock(), memory=MagicMock(), raft=rafts[node_id],
            )
            for node_id in peers
        }

        rafts["a"]._start_election()
        self.assertTrue(clusters["a"].assign_task("work-1", "a", lease_seconds=1))
        rafts["a"]._send_heartbeats()  # propagate the leader commit to followers
        self.assertEqual(clusters["b"].task_state._tasks["work-1"]["status"], "leased")

        rpc.unavailable.add("a")
        rafts["b"]._start_election()
        self.assertEqual(rafts["b"].role, Role.LEADER)
        clusters["b"].requeue_expired_tasks(now=10**12)
        rafts["b"]._send_heartbeats()
        rafts["b"]._send_heartbeats()
        self.assertEqual(clusters["b"].task_state._tasks["work-1"]["status"], "pending")

        self.assertTrue(clusters["b"].assign_task("work-1", "b", lease_seconds=30))
        rafts["b"]._send_heartbeats()
        self.assertEqual(clusters["b"].task_state._tasks["work-1"]["assignee"], "b")
        self.assertEqual(clusters["c"].task_state._tasks["work-1"]["assignee"], "b")
        self.assertEqual(rafts["b"].commit_index, rafts["c"].commit_index)
        self.assertEqual(
            [entry.command for entry in rafts["b"].log],
            [entry.command for entry in rafts["c"].log],
        )
        self.assertLess(rafts["a"].commit_index, rafts["b"].commit_index)

    def test_governance_metadata_commits_and_converges_without_copying_sensitive_payloads(self):
        from infrastructure.cluster_network.raft_cluster_node import RaftClusterNode
        from infrastructure.cluster_network.trust_store import TrustStore

        rpc = _InProcessRaftRpc()
        peers = {"a": ["b", "c"], "b": ["a", "c"], "c": ["a", "b"]}
        rafts = {node_id: RaftNode(node_id, get_peer_ids=lambda node_id=node_id: peers[node_id], rpc_client=rpc) for node_id in peers}
        rpc.nodes = rafts
        clusters = {
            node_id: RaftClusterNode(
                node_id=f"governance-{node_id}", transport_node_id=node_id,
                trust_store=TrustStore(f"/tmp/reus-governance-{node_id}-peers.json"),
                capabilities=MagicMock(), memory=MagicMock(), raft=rafts[node_id],
            )
            for node_id in peers
        }

        rafts["a"]._start_election()
        self.assertTrue(
            clusters["a"].record_governance_decision(
                "decision-1", "autonomy.proposal.approve", "approved", "a" * 64, "b" * 64
            )
        )
        rafts["a"]._send_heartbeats()
        rafts["a"]._send_heartbeats()

        for node_id in ("a", "b", "c"):
            decision = clusters[node_id].governance_state._decisions["decision-1"]
            self.assertEqual(decision["status"], "approved")
            self.assertEqual(decision["actor_hash"], "a" * 64)
            self.assertNotIn("payload", decision)
            self.assertNotIn("chat_id", decision)
        self.assertEqual(rafts["a"].commit_index, rafts["b"].commit_index)
        self.assertEqual(rafts["b"].commit_index, rafts["c"].commit_index)


if __name__ == "__main__":
    unittest.main()
