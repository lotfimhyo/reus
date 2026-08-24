"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Composes the snapshot service and Raft state machine into the node delegate
served exclusively over mTLS.  The certificate CN is checked against every
claimed Raft sender identifier before reaching the consensus algorithm.
"""
from __future__ import annotations

from infrastructure.cluster_network.cluster_snapshot_node import ClusterSnapshotNode
from infrastructure.cluster_network.raft import LogEntry, RaftNode
from infrastructure.cluster_network.recovery import CellRecoveryPlanner
import time


class ReplicatedDecisionState:
    """Small, deterministic state machine for committed coordination facts."""

    def __init__(self):
        self._commands: dict[int, dict] = {}

    def apply(self, entry: LogEntry) -> None:
        self._commands[entry.index] = dict(entry.command)

    def snapshot(self) -> dict:
        return {"commands": [{"index": index, "command": command} for index, command in self._commands.items()]}

    def restore(self, data: dict) -> None:
        restored: dict[int, dict] = {}
        for item in data.get("commands", []):
            if isinstance(item, dict) and isinstance(item.get("index"), int) and isinstance(item.get("command"), dict):
                restored[item["index"]] = item["command"]
        self._commands = restored

    def status(self) -> dict:
        return {"committed_commands": len(self._commands)}


class ReplicatedTaskLeaseState:
    """Deterministic, non-secret task assignment state replicated by Raft."""
    def __init__(self): self._tasks: dict[str, dict] = {}; self._evidence: dict[str, dict] = {}

    def apply(self, entry: LogEntry) -> None:
        command = entry.command
        if command.get("kind") == "task_assign" and isinstance(command.get("task_id"), str):
            self._tasks[command["task_id"]] = {"status": "leased", "assignee": command.get("assignee"), "lease_until": float(command.get("lease_until", 0)), "attempt": int(command.get("attempt", 1))}
        elif command.get("kind") == "task_complete" and command.get("task_id") in self._tasks:
            self._tasks[command["task_id"]]["status"] = "completed"
        elif command.get("kind") == "task_requeue" and command.get("task_id") in self._tasks:
            self._tasks[command["task_id"]].update({"status": "pending", "assignee": None, "lease_until": 0})
        elif command.get("kind") == "evidence_publish" and isinstance(command.get("evidence_id"), str):
            self._evidence[command["evidence_id"]] = {key: command[key] for key in ("summary", "source_hash", "confidence") if key in command}

    def expired_task_ids(self, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        return [task_id for task_id, task in self._tasks.items() if task.get("status") == "leased" and float(task.get("lease_until", 0)) <= now]

    def snapshot(self) -> dict: return {"tasks": self._tasks, "approved_evidence": self._evidence}
    def restore(self, data: dict) -> None: self._tasks = {str(key): dict(value) for key, value in data.get("tasks", {}).items() if isinstance(value, dict)}; self._evidence = {str(key): dict(value) for key, value in data.get("approved_evidence", {}).items() if isinstance(value, dict)}
    def status(self) -> dict: return {"tracked_tasks": len(self._tasks), "leased_tasks": sum(1 for task in self._tasks.values() if task.get("status") == "leased"), "approved_evidence_summaries": len(self._evidence)}


class ReplicatedGovernanceDecisionState:
    """Raft-replicated, non-secret audit metadata for cross-node governance."""

    _allowed_statuses = {"proposed", "approved", "rejected", "executed"}

    def __init__(self) -> None:
        self._decisions: dict[str, dict] = {}

    def apply(self, entry: LogEntry) -> None:
        command = entry.command
        if command.get("kind") != "governance_decision" or not isinstance(command.get("decision_id"), str):
            return
        status = command.get("status")
        if status not in self._allowed_statuses:
            return
        self._decisions[command["decision_id"]] = {
            key: command[key]
            for key in ("action", "status", "actor_hash", "subject_hash")
            if isinstance(command.get(key), str)
        } | {"committed_index": entry.index}

    def snapshot(self) -> dict:
        return {"governance_decisions": self._decisions}

    def restore(self, data: dict) -> None:
        decisions = data.get("governance_decisions", {})
        self._decisions = {str(key): dict(value) for key, value in decisions.items() if isinstance(value, dict)}

    def status(self) -> dict:
        return {"replicated_governance_decisions": len(self._decisions)}


class RaftClusterNode(ClusterSnapshotNode):
    def __init__(self, *, raft: RaftNode, transport_node_id: str, **kwargs):
        super().__init__(**kwargs)
        self.raft = raft
        self.transport_node_id = transport_node_id
        self.decision_state = ReplicatedDecisionState(); self.peer_liveness: dict[str, dict] = {}
        self.task_state = ReplicatedTaskLeaseState()
        self.governance_state = ReplicatedGovernanceDecisionState()
        self._recovery_planner: CellRecoveryPlanner | None = None
        self._standby_transport_ids: set[str] = set()
        self.raft.on_commit = self._apply_commit
        self.raft.get_snapshot_data = self._snapshot
        self.raft.on_snapshot_restore = self._restore
        self.raft.on_leader_tick = self.requeue_expired_tasks
        self.raft.on_peer_liveness = self._record_peer_liveness
        if self.raft.restored_snapshot_data is not None:
            self._restore(self.raft.restored_snapshot_data)
        self.raft.replay_committed()

    def _sender_matches(self, body: dict, sender_cn: str | None, key: str) -> bool:
        return isinstance(sender_cn, str) and sender_cn == body.get(key)

    def handle_request_vote(self, body: dict, sender_cn: str | None) -> dict:
        if not self._sender_matches(body, sender_cn, "candidate_id"):
            return {"term": self.raft.current_term, "vote_granted": False, "error": "mTLS sender mismatch"}
        try:
            term, granted = self.raft.handle_request_vote(
                int(body["term"]), body["candidate_id"], int(body["last_log_index"]), int(body["last_log_term"])
            )
            return {"term": term, "vote_granted": granted}
        except (KeyError, TypeError, ValueError):
            return {"term": self.raft.current_term, "vote_granted": False, "error": "invalid vote request"}

    def handle_append_entries(self, body: dict, sender_cn: str | None) -> dict:
        if not self._sender_matches(body, sender_cn, "leader_id"):
            return {"term": self.raft.current_term, "success": False, "error": "mTLS sender mismatch"}
        try:
            term, success = self.raft.handle_append_entries(
                int(body["term"]), body["leader_id"], int(body["prev_log_index"]), int(body["prev_log_term"]),
                body["entries"], int(body["leader_commit"]),
            )
            return {"term": term, "success": success}
        except (KeyError, TypeError, ValueError):
            return {"term": self.raft.current_term, "success": False, "error": "invalid append request"}

    def handle_install_snapshot(self, body: dict, sender_cn: str | None) -> dict:
        if not self._sender_matches(body, sender_cn, "leader_id"):
            return {"term": self.raft.current_term, "success": False, "error": "mTLS sender mismatch"}
        try:
            term, success = self.raft.handle_install_snapshot(
                int(body["term"]), body["leader_id"], int(body["last_included_index"]),
                int(body["last_included_term"]), body["snapshot_data"], body.get("membership"),
            )
            return {"term": term, "success": success}
        except (KeyError, TypeError, ValueError):
            return {"term": self.raft.current_term, "success": False, "error": "invalid snapshot request"}

    def cluster_status(self) -> dict:
        return {**self.raft.status(), **self.decision_state.status(), **self.task_state.status(), **self.governance_state.status(), "transport_node_id": self.transport_node_id, "peers": self.peer_liveness}

    def handle_cluster_snapshot(self, body: dict, sender_cn: str | None) -> dict:
        snapshot = super().handle_cluster_snapshot(body, sender_cn)
        snapshot["raft_membership"] = self.raft.membership_snapshot()
        return snapshot

    def assign_task(self, task_id: str, assignee: str, lease_seconds: float = 30.0) -> bool:
        return self.raft.propose_and_wait({"kind": "task_assign", "task_id": task_id, "assignee": assignee, "lease_until": time.time() + max(1.0, lease_seconds), "attempt": 1})

    def complete_task(self, task_id: str) -> bool:
        return self.raft.propose_and_wait({"kind": "task_complete", "task_id": task_id})

    def admit_trusted_peer(self, transport_node_id: str) -> bool:
        """Promote an mTLS-trusted peer into this cell through joint consensus."""
        if self.trust_store.get_peer_by_transport_id(transport_node_id) is None:
            return False
        voters = set(self.raft.status()["voters"])
        voters.add(transport_node_id)
        return self.raft.propose_membership_change(sorted(voters))

    def register_trusted_learner(self, transport_node_id: str) -> bool:
        """Replicate to a pre-approved standby before it can receive a vote."""
        if self.trust_store.get_peer_by_transport_id(transport_node_id) is None:
            return False
        return self.raft.register_learner(transport_node_id)

    def configure_automatic_recovery(
        self,
        standby_transport_ids: list[str],
        *,
        failure_threshold: int = 3,
        minimum_suspect_seconds: float = 5.0,
    ) -> bool:
        """Enable recovery with explicitly trusted standby peers only.

        This never creates machines or grants mTLS trust; the normal human
        approval workflow must register every standby before this method runs.
        """
        standby_ids = set(standby_transport_ids)
        if not standby_ids or any(self.trust_store.get_peer_by_transport_id(peer_id) is None for peer_id in standby_ids):
            return False
        self._recovery_planner = CellRecoveryPlanner(
            failure_threshold=failure_threshold,
            minimum_suspect_seconds=minimum_suspect_seconds,
        )
        self._standby_transport_ids = standby_ids
        return all(self.raft.register_learner(peer_id) or self.raft.is_learner(peer_id) for peer_id in standby_ids)

    def replace_failed_peer(self, failed_transport_node_id: str, standby_transport_node_id: str) -> bool:
        """Atomically replace one cell voter with an already-trusted standby."""
        if self.trust_store.get_peer_by_transport_id(standby_transport_node_id) is None:
            return False
        if self.peer_liveness.get(standby_transport_node_id, {}).get("alive") is not True:
            return False
        voters = set(self.raft.status()["voters"])
        if failed_transport_node_id not in voters or standby_transport_node_id in voters:
            return False
        voters.remove(failed_transport_node_id)
        voters.add(standby_transport_node_id)
        return self.raft.propose_membership_change(sorted(voters))

    def publish_evidence_summary(self, evidence_id: str, summary: str, source_hash: str, confidence: float) -> bool:
        if len(summary) > 2_000 or len(source_hash) > 128: return False
        return self.raft.propose({"kind": "evidence_publish", "evidence_id": evidence_id, "summary": summary, "source_hash": source_hash, "confidence": max(0.0, min(1.0, confidence))})

    @staticmethod
    def _is_sha256(value: str) -> bool:
        return len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())

    def record_governance_decision(self, decision_id: str, action: str, status: str, actor_hash: str, subject_hash: str) -> bool:
        """Commit review metadata without copying callback payloads, chat IDs, or secrets."""
        if (
            not decision_id
            or len(decision_id) > 128
            or not action
            or len(action) > 96
            or status not in ReplicatedGovernanceDecisionState._allowed_statuses
            or not self._is_sha256(actor_hash)
            or not self._is_sha256(subject_hash)
        ):
            return False
        return self.raft.propose_and_wait(
            {
                "kind": "governance_decision",
                "decision_id": decision_id,
                "action": action,
                "status": status,
                "actor_hash": actor_hash.lower(),
                "subject_hash": subject_hash.lower(),
            }
        )

    def requeue_expired_tasks(self, now: float | None = None) -> None:
        """Propose requeue decisions for expired leases; ``now`` enables deterministic tests."""
        for task_id in self.task_state.expired_task_ids(now):
            self.raft.propose({"kind": "task_requeue", "task_id": task_id, "reason": "lease_expired"})

    def _record_peer_liveness(self, peer_id: str, alive: bool) -> None:
        self.peer_liveness[peer_id] = {"alive": alive, "observed_at": time.time()}
        # Failure observation is local/operational, while the resulting task
        # requeue is a normal Raft decision.  Only the leader may propose it.
        task_state = getattr(self, "task_state", None)
        raft = getattr(self, "raft", None)
        if not alive and task_state is not None and raft is not None:
            for task_id, task in task_state._tasks.items():
                if task.get("status") == "leased" and task.get("assignee") == peer_id:
                    raft.propose({"kind": "task_requeue", "task_id": task_id, "reason": "peer_unreachable"})
        planner = getattr(self, "_recovery_planner", None)
        if planner is None or raft is None:
            return
        ready_standbys = {
            standby_id
            for standby_id in self._standby_transport_ids
            if raft.is_learner(standby_id) and self.peer_liveness.get(standby_id, {}).get("alive") is True
        }
        plan = planner.observe(
            peer_id,
            alive,
            voters=set(raft.status()["voters"]),
            ready_standbys=ready_standbys,
        )
        if plan is not None:
            if self.replace_failed_peer(plan.failed_voter_id, plan.standby_voter_id):
                planner.resolve(plan.failed_voter_id)
            else:
                planner.retry(plan.failed_voter_id)

    def _apply_commit(self, entry: LogEntry) -> None:
        self.decision_state.apply(entry); self.task_state.apply(entry); self.governance_state.apply(entry)

    def _snapshot(self) -> dict:
        return {**self.decision_state.snapshot(), **self.task_state.snapshot(), **self.governance_state.snapshot()}

    def _restore(self, data: dict) -> None:
        self.decision_state.restore(data); self.task_state.restore(data); self.governance_state.restore(data)
