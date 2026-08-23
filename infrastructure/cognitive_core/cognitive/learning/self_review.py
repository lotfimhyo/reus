"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

SelfReview — step 8 of the cognitive cycle from the master architecture
document, section "Cognitive Engine" (self-review), deferred at the end of
Layer 5's first increment specifically because it needed a real population
of executed goals to review. That population now exists as audited,
Episodic Memory records produced by every CognitiveEngine.run() call since.

Design decision: review is computed fresh from Episodic Memory on every
call rather than maintained as running counters, because Episodic Memory is
already the append-only source of truth (per master doc section 2.3) —
keeping a second, separately-updated counter would be a second source of
truth that could drift from it. Recomputing is cheap at Local Mode data
volumes; if/when volume ever makes that untrue, that is itself a Hybrid/
Cloud-mode-era optimization problem, not one to pre-solve speculatively now.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from infrastructure.cognitive_core.memory import MemoryLayer

_COMPLETED_ACTION = "goal.completed"
_FAILED_ACTION = "goal.failed_execution"


@dataclass(frozen=True)
class ReviewReport:
    """The outcome of reviewing one capability's execution history."""

    capability_id: str
    total_runs: int
    successes: int
    failures: int
    success_rate: Optional[float]  # None when total_runs == 0 — "no data yet"
    failure_reasons: dict[str, int] = field(default_factory=dict)


class SelfReview:
    """Reviews how a capability has actually performed, by scanning
    Episodic Memory's completed/failed execution records."""

    def __init__(self, memory: MemoryLayer):
        self.memory = memory

    def review_capability(self, capability_id: str, limit: int = 1000) -> ReviewReport:
        completed = self.memory.episodes_by_action(_COMPLETED_ACTION, limit=limit)
        failed = self.memory.episodes_by_action(_FAILED_ACTION, limit=limit)

        matching_completed = [
            e for e in completed if e.payload.get("capability_id") == capability_id
        ]
        matching_failed = [
            e for e in failed if e.payload.get("capability_id") == capability_id
        ]

        successes = len(matching_completed)
        failures = len(matching_failed)
        total = successes + failures

        reasons = Counter(
            (e.result or {}).get("error") or "unknown_error" for e in matching_failed
        )

        return ReviewReport(
            capability_id=capability_id,
            total_runs=total,
            successes=successes,
            failures=failures,
            success_rate=(successes / total) if total > 0 else None,
            failure_reasons=dict(reasons),
        )
