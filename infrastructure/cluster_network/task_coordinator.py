"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

The task coordinator is the narrow bridge between committed Raft task leases
and local capability execution.  It deliberately carries task metadata only;
payloads and raw memory are never replicated.
"""
from __future__ import annotations

from typing import Any

from infrastructure.cluster_network.raft_cluster_node import RaftClusterNode
from infrastructure.cognitive_core.resource.local_executor import HandlerResult, LocalExecutor


class ClusterTaskCoordinator:
    """Execute locally only after a committed Raft lease has been assigned."""

    def __init__(self, *, cluster: RaftClusterNode, executor: LocalExecutor, assignee_id: str):
        self._cluster = cluster
        self._executor = executor
        self._assignee_id = assignee_id

    def acquire(self, task_id: str, *, lease_seconds: float = 30.0) -> bool:
        """Commit this node's right to run a non-secret task."""
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        return self._cluster.assign_task(task_id, self._assignee_id, lease_seconds)

    def complete(self, task_id: str) -> bool:
        """Commit completion before a caller exposes a successful result."""
        return self._cluster.complete_task(task_id)

    def execute(self, task_id: str, step: Any, payload: dict[str, Any], *, lease_seconds: float = 30.0) -> HandlerResult:
        if not self.acquire(task_id, lease_seconds=lease_seconds):
            return HandlerResult(False, {}, "Task lease was not committed by the cluster leader.")
        result = self._executor(step, payload)
        if result.success and not self.complete(task_id):
            return HandlerResult(False, {}, "Task ran locally but completion was not committed; result is withheld.")
        return result
