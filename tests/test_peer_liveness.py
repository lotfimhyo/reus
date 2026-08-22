# Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink
from infrastructure.cluster_network.raft_cluster_node import RaftClusterNode
from infrastructure.cluster_network.raft import LogEntry, RaftNode, Role
from infrastructure.cluster_network.trust_store import TrustStore
from unittest.mock import MagicMock


def test_peer_liveness_record_is_operational_not_replicated_decision():
    node = object.__new__(RaftClusterNode)
    node.peer_liveness = {}
    node._record_peer_liveness("peer-a", False)
    assert node.peer_liveness["peer-a"]["alive"] is False
    node._record_peer_liveness("peer-a", True)
    assert node.peer_liveness["peer-a"]["alive"] is True


def test_unreachable_peer_requeues_its_leased_task_through_leader_raft_log(tmp_path):
    raft = RaftNode(node_id="leader", get_peer_ids=lambda: [], rpc_client=MagicMock())
    raft.current_term = 1
    raft.role = Role.LEADER
    node = RaftClusterNode(
        node_id="component-leader", transport_node_id="leader",
        trust_store=TrustStore(str(tmp_path / "peers.json")), capabilities=MagicMock(), memory=MagicMock(), raft=raft,
    )
    node.task_state.apply(LogEntry(term=1, index=0, command={"kind": "task_assign", "task_id": "t1", "assignee": "peer-a", "lease_until": 9999999999}))

    node._record_peer_liveness("peer-a", False)

    assert node.peer_liveness["peer-a"]["alive"] is False
    assert raft.log[-1].command == {"kind": "task_requeue", "task_id": "t1", "reason": "peer_unreachable"}


def test_failed_heartbeat_triggers_liveness_callback_and_lease_requeue(tmp_path):
    rpc = MagicMock()
    rpc.append_entries.side_effect = ConnectionError("peer unavailable")
    raft = RaftNode(node_id="leader", get_peer_ids=lambda: ["peer-a"], rpc_client=rpc)
    raft.current_term = 1
    raft.role = Role.LEADER
    raft.leader_id = "leader"
    node = RaftClusterNode(
        node_id="component-leader", transport_node_id="leader",
        trust_store=TrustStore(str(tmp_path / "peers.json")), capabilities=MagicMock(), memory=MagicMock(), raft=raft,
    )
    node.task_state.apply(LogEntry(term=1, index=0, command={"kind": "task_assign", "task_id": "t1", "assignee": "peer-a", "lease_until": 9999999999}))

    raft._send_heartbeats()

    assert node.peer_liveness["peer-a"]["alive"] is False
    assert any(entry.command.get("reason") == "peer_unreachable" for entry in raft.log)
