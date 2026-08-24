# Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink
from unittest.mock import MagicMock

from infrastructure.cluster_network.raft import RaftNode, Role
from infrastructure.cluster_network.raft_cluster_node import RaftClusterNode
from infrastructure.cluster_network.recovery import CellRecoveryPlanner


def test_recovery_planner_ignores_transient_failure_then_selects_ready_standby():
    planner = CellRecoveryPlanner(failure_threshold=3, minimum_suspect_seconds=5)
    voters = {"leader", "peer-a", "peer-b"}

    assert planner.observe("peer-a", False, voters=voters, ready_standbys={"standby-z"}, now=0) is None
    assert planner.observe("peer-a", False, voters=voters, ready_standbys={"standby-z"}, now=2) is None
    plan = planner.observe("peer-a", False, voters=voters, ready_standbys={"standby-z"}, now=5)

    assert plan is not None
    assert plan.failed_voter_id == "peer-a"
    assert plan.standby_voter_id == "standby-z"
    assert planner.observe("peer-a", False, voters=voters, ready_standbys={"standby-z"}, now=6) is None


def test_automatic_recovery_replaces_only_a_trusted_live_learner():
    trust_store = MagicMock()
    trust_store.get_peer_by_transport_id.return_value = {"host": "127.0.0.1", "port": 8443}
    raft = RaftNode("leader", get_peer_ids=lambda: ["failed"], rpc_client=MagicMock())
    raft.role = Role.LEADER
    raft.current_term = 1
    raft.propose_membership_change = MagicMock(return_value=True)
    node = RaftClusterNode(
        node_id="component-leader",
        transport_node_id="leader",
        trust_store=trust_store,
        capabilities=MagicMock(),
        memory=MagicMock(),
        raft=raft,
    )

    assert node.configure_automatic_recovery(["standby"], failure_threshold=1, minimum_suspect_seconds=0)
    node._record_peer_liveness("standby", True)
    node._record_peer_liveness("failed", False)

    raft.propose_membership_change.assert_called_once_with(["leader", "standby"])


def test_automatic_recovery_refuses_untrusted_or_unhealthy_standby():
    trust_store = MagicMock()
    trust_store.get_peer_by_transport_id.return_value = None
    raft = RaftNode("leader", get_peer_ids=lambda: ["failed"], rpc_client=MagicMock())
    node = RaftClusterNode(
        node_id="component-leader",
        transport_node_id="leader",
        trust_store=trust_store,
        capabilities=MagicMock(),
        memory=MagicMock(),
        raft=raft,
    )

    assert not node.configure_automatic_recovery(["untrusted"])
