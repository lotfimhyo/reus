# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""Select the most suitable model for a task from a known profile registry.

Routing is deterministic and fully local: it evaluates required capabilities,
cost ceiling, and context size without network access. A separate
`ModelProvider` layer performs the selected model's actual invocation.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class NoSuitableModel(Exception):
    def __init__(self, reason: str):
        super().__init__(f"No suitable model: {reason}")


@dataclass(frozen=True)
class ModelProfile:
    """Known technical and economic characteristics of one model."""

    name: str
    provider: str
    capability_tags: frozenset[str]
    input_cost_per_1k_tokens_usd: float
    output_cost_per_1k_tokens_usd: float
    max_context_tokens: int
    # Relative response-speed estimate (1 is fastest), used only to rank ties.
    relative_speed_rank: int


@dataclass
class TaskRequirements:
    """What a task requires from a model, not a model identity."""

    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    min_context_tokens: int = 0
    max_input_cost_per_1k_tokens_usd: float | None = None
    prefer: str = "cheapest"  # "cheapest" | "fastest" | "most_capable"


class ModelRouter:
    def __init__(self, profiles: list[ModelProfile]) -> None:
        if not profiles:
            raise ValueError("ModelRouter requires at least one registered model.")
        self._profiles = list(profiles)

    def list_profiles(self) -> list[ModelProfile]:
        return list(self._profiles)

    def select(self, requirements: TaskRequirements) -> ModelProfile:
        candidates = [p for p in self._profiles if requirements.required_capabilities <= p.capability_tags]
        if not candidates:
            raise NoSuitableModel(
                f"no model has every required capability: {sorted(requirements.required_capabilities)}"
            )

        candidates = [p for p in candidates if p.max_context_tokens >= requirements.min_context_tokens]
        if not candidates:
            raise NoSuitableModel(f"no model has a context window of {requirements.min_context_tokens} tokens")

        if requirements.max_input_cost_per_1k_tokens_usd is not None:
            candidates = [
                p for p in candidates if p.input_cost_per_1k_tokens_usd <= requirements.max_input_cost_per_1k_tokens_usd
            ]
            if not candidates:
                raise NoSuitableModel(
                    f"no model is within the input-cost ceiling of ${requirements.max_input_cost_per_1k_tokens_usd} per 1,000 tokens"
                )

        if requirements.prefer == "fastest":
            return min(candidates, key=lambda p: p.relative_speed_rank)
        if requirements.prefer == "most_capable":
            return max(candidates, key=lambda p: len(p.capability_tags))
        # Default: cheapest input, then cheapest output as a tie-breaker.
        return min(candidates, key=lambda p: (p.input_cost_per_1k_tokens_usd, p.output_cost_per_1k_tokens_usd))
