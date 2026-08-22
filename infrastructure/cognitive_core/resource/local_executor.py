"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

LocalExecutor — the first real (non-mock) Executor for the Cognitive Engine
(Layer 5), backed by this layer's TaskScheduler + SandboxedExecutor.

Design decision (dependency direction): the master architecture doc's
layer stack places Resource & Execution (Layer 2) *below* Cognitive Engine
(Layer 5). Clean layering means lower layers must not import from higher
ones. So this module does NOT import infrastructure.cognitive_core.cognitive.* at all — instead
it returns its own HandlerResult, whose fields (success, output, error)
intentionally mirror infrastructure.cognitive_core.cognitive.execution.ExecutionResult exactly.
Because CognitiveEngine only ever accesses `.success` / `.output` / `.error`
on whatever the Executor returns (structural typing, not an isinstance
check), a LocalExecutor instance is already a valid Executor for
CognitiveEngine.run() with zero adapter code needed — see the integration
test and README for a worked example.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from infrastructure.cognitive_core.resource.scheduler import TaskScheduler


@dataclass(frozen=True)
class HandlerResult:
    """Same shape as infrastructure.cognitive_core.cognitive.execution.ExecutionResult, by
    design — see module docstring."""

    success: bool
    output: dict[str, Any]
    error: Optional[str] = None


class LocalExecutor:
    """
    Maps capability_id -> a plain handler function (the capability's actual
    business logic, supplied by whoever implements that agent/tool), and
    runs it through the sandboxed TaskScheduler when invoked.

    Instances are callable with the same (step, payload) shape the
    Cognitive Engine's Executor expects: `step` only needs a
    `capability_id` attribute (duck-typed — no import of PlanStep needed).
    """

    def __init__(
        self,
        scheduler: Optional[TaskScheduler] = None,
        timeout_seconds: float = 30.0,
        memory_limit_mb: Optional[int] = 256,
    ):
        self.scheduler = scheduler or TaskScheduler()
        self.timeout_seconds = timeout_seconds
        self.memory_limit_mb = memory_limit_mb
        self._handlers: dict[str, Callable[[dict], dict]] = {}

    def register_handler(
        self, capability_id: str, handler: Callable[[dict], dict]
    ) -> None:
        """Bind a capability_id (from the Capability Registry) to the
        function that actually performs it."""
        self._handlers[capability_id] = handler

    def is_registered(self, capability_id: str) -> bool:
        return capability_id in self._handlers

    def shutdown(self) -> None:
        """Uniform lifecycle method — VeritasSystem.close() calls this
        without needing to know whether it holds a LocalExecutor or a
        ClusterExecutor wrapping one (see cluster/cluster_executor.py)."""
        self.scheduler.shutdown()

    def __call__(self, step: Any, payload: dict) -> HandlerResult:
        handler = self._handlers.get(step.capability_id)
        if handler is None:
            return HandlerResult(
                success=False,
                output={},
                error=f"No handler registered for capability_id={step.capability_id!r}.",
            )

        future = self.scheduler.submit(
            handler, payload, self.timeout_seconds, self.memory_limit_mb
        )
        outcome = future.result()

        if outcome.status == "ok":
            return HandlerResult(success=True, output=outcome.data, error=None)
        return HandlerResult(success=False, output={}, error=str(outcome.data))
