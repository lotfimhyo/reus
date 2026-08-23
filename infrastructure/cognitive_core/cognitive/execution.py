"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Execution — step 6 of the cognitive cycle (execution) from the master
architecture document, section 2.5.

Design decision: the Cognitive Engine does NOT itself know how to run a
capability — actually invoking an agent/tool, sandboxing it, and managing
its resources is the Resource & Execution Layer's job (Layer 2), which is
a separate, not-yet-built increment. To keep this layer's boundary clean
("no leaky abstractions"), the engine accepts an injected `Executor`
callable and delegates all real work to it. This also makes the engine
fully testable without any real agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from infrastructure.cognitive_core.cognitive.plan import PlanStep


@dataclass(frozen=True)
class ExecutionResult:
    """The outcome of running a single plan step."""

    success: bool
    output: dict[str, Any]
    error: Optional[str] = None


# An Executor receives the chosen PlanStep and the goal's input payload,
# and returns an ExecutionResult. Supplied by the caller (ultimately backed
# by Layer 2 in a future increment); the engine never inspects how it works.
Executor = Callable[[PlanStep, dict[str, Any]], ExecutionResult]
