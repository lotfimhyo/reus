"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Deterministic planning for a small Raft cell's local failover.  The planner
does not provision machines, grant trust, or change membership by itself.
It only emits one replacement plan after repeated failure observations; the
Raft leader must still commit the replacement through joint consensus.
"""
from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass(frozen=True)
class ReplacementPlan:
    failed_voter_id: str
    standby_voter_id: str
    observed_failures: int
    first_failure_at: float


@dataclass
class _FailureWindow:
    count: int
    first_failure_at: float


class CellRecoveryPlanner:
    def __init__(self, *, failure_threshold: int = 3, minimum_suspect_seconds: float = 5.0) -> None:
        if failure_threshold < 1 or minimum_suspect_seconds < 0:
            raise ValueError("recovery thresholds must be non-negative and failure_threshold must be positive")
        self._failure_threshold = failure_threshold
        self._minimum_suspect_seconds = minimum_suspect_seconds
        self._failures: dict[str, _FailureWindow] = {}
        self._planned_failures: set[str] = set()

    def observe(
        self,
        peer_id: str,
        alive: bool,
        *,
        voters: set[str],
        ready_standbys: set[str],
        now: float | None = None,
    ) -> ReplacementPlan | None:
        now = time.time() if now is None else now
        if alive:
            self._failures.pop(peer_id, None)
            self._planned_failures.discard(peer_id)
            return None
        if peer_id not in voters or peer_id in self._planned_failures:
            return None
        window = self._failures.get(peer_id)
        if window is None:
            window = _FailureWindow(count=0, first_failure_at=now)
        window.count += 1
        self._failures[peer_id] = window
        if window.count < self._failure_threshold or now - window.first_failure_at < self._minimum_suspect_seconds:
            return None
        candidates = sorted(ready_standbys - voters - {peer_id})
        if not candidates:
            return None
        self._planned_failures.add(peer_id)
        return ReplacementPlan(peer_id, candidates[0], window.count, window.first_failure_at)

    def retry(self, failed_voter_id: str) -> None:
        """Allow a retry after a failed Raft proposal without forgetting evidence."""
        self._planned_failures.discard(failed_voter_id)

    def resolve(self, failed_voter_id: str) -> None:
        self._planned_failures.discard(failed_voter_id)
        self._failures.pop(failed_voter_id, None)
