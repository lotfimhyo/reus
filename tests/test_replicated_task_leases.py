# Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink
from infrastructure.cluster_network.raft import LogEntry
from infrastructure.cluster_network.raft_cluster_node import ReplicatedTaskLeaseState


def test_task_lease_state_requeues_only_expired_leases_and_preserves_completed_tasks():
    state = ReplicatedTaskLeaseState()
    state.apply(LogEntry(term=1, index=0, command={"kind": "task_assign", "task_id": "expired", "assignee": "n1", "lease_until": 10, "attempt": 1}))
    state.apply(LogEntry(term=1, index=1, command={"kind": "task_assign", "task_id": "done", "assignee": "n2", "lease_until": 10, "attempt": 1}))
    state.apply(LogEntry(term=1, index=2, command={"kind": "task_complete", "task_id": "done"}))
    assert state.expired_task_ids(now=11) == ["expired"]
    state.apply(LogEntry(term=2, index=3, command={"kind": "task_requeue", "task_id": "expired"}))
    assert state.expired_task_ids(now=99) == []
    state.apply(LogEntry(term=2, index=4, command={"kind": "evidence_publish", "evidence_id": "e-1", "summary": "ملخص معتمد", "source_hash": "abc", "confidence": 0.9, "raw": "must-not-copy"}))
    snapshot = state.snapshot()
    assert snapshot["approved_evidence"] == {"e-1": {"summary": "ملخص معتمد", "source_hash": "abc", "confidence": 0.9}}
    assert state.status() == {"tracked_tasks": 2, "leased_tasks": 0, "approved_evidence_summaries": 1}
