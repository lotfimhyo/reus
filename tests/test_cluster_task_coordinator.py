"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from infrastructure.cluster_network.raft import RaftNode, Role
from infrastructure.cluster_network.raft_cluster_node import RaftClusterNode
from infrastructure.cluster_network.task_coordinator import ClusterTaskCoordinator
from infrastructure.cluster_network.trust_store import TrustStore
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor


def test_committed_lease_precedes_execution_and_committed_completion_follows_it(tmp_path):
    raft = RaftNode(node_id="n1", get_peer_ids=lambda: [], rpc_client=MagicMock())
    raft.current_term = 1
    raft.role = Role.LEADER
    cluster = RaftClusterNode(
        node_id="component-1", trust_store=TrustStore(str(tmp_path / "peers.json")),
        capabilities=MagicMock(), memory=MagicMock(), raft=raft, transport_node_id="n1",
    )
    executor = LocalExecutor()
    executor.register_handler("echo", lambda payload: {"echo": payload["value"]})
    coordinator = ClusterTaskCoordinator(cluster=cluster, executor=executor, assignee_id="n1")

    result = coordinator.execute("task-1", SimpleNamespace(capability_id="echo"), {"value": "ok"})

    assert result.success is True
    assert result.output == {"echo": "ok"}
    assert cluster.task_state._tasks["task-1"]["status"] == "completed"
    assert raft.commit_index == 1


def test_execution_is_not_called_when_lease_cannot_be_committed(tmp_path):
    raft = RaftNode(node_id="n1", get_peer_ids=lambda: [], rpc_client=MagicMock())
    cluster = RaftClusterNode(
        node_id="component-1", trust_store=TrustStore(str(tmp_path / "peers.json")),
        capabilities=MagicMock(), memory=MagicMock(), raft=raft, transport_node_id="n1",
    )
    executor = LocalExecutor()
    handler = MagicMock(return_value={"unexpected": True})
    executor.register_handler("echo", handler)

    result = ClusterTaskCoordinator(cluster=cluster, executor=executor, assignee_id="n1").execute(
        "task-1", SimpleNamespace(capability_id="echo"), {}
    )

    assert result.success is False
    assert "lease" in (result.error or "").lower()
    handler.assert_not_called()
