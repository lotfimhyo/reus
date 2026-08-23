# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Default multi-provider model registry for Anthropic, OpenAI, Google, and Kimi.

Important accuracy note: the cost fields are **relative estimates for ordering
only**, not official pricing suitable for billing. A production operator must
replace them with current values from each provider's official pricing page
before making real cost decisions. These values preserve only an intended
relative ordering within each model family.

OpenAI and Google profiles exist because ModelRouter is provider-agnostic by
design. In this constrained development environment, their live clients were
not network-validated; see infrastructure/model_client.py. This registry does
not claim external availability, pricing accuracy, or model validation.
"""
from __future__ import annotations

from application.model_router import ModelProfile, ModelRouter

DEFAULT_MODEL_PROFILES: list[ModelProfile] = [
    # --- Anthropic ---
    ModelProfile(
        name="claude-haiku-4-5-20251001",
        provider="anthropic",
        capability_tags=frozenset({"chat", "summarization", "classification", "fast"}),
        input_cost_per_1k_tokens_usd=0.001,
        output_cost_per_1k_tokens_usd=0.005,
        max_context_tokens=200_000,
        relative_speed_rank=1,
    ),
    ModelProfile(
        name="claude-sonnet-5",
        provider="anthropic",
        capability_tags=frozenset({"chat", "summarization", "classification", "reasoning", "code", "fast"}),
        input_cost_per_1k_tokens_usd=0.003,
        output_cost_per_1k_tokens_usd=0.015,
        max_context_tokens=200_000,
        relative_speed_rank=2,
    ),
    ModelProfile(
        name="claude-opus-4-8",
        provider="anthropic",
        capability_tags=frozenset({"chat", "summarization", "classification", "reasoning", "code", "deep-research"}),
        input_cost_per_1k_tokens_usd=0.015,
        output_cost_per_1k_tokens_usd=0.075,
        max_context_tokens=200_000,
        relative_speed_rank=3,
    ),
    # --- OpenAI ---
    ModelProfile(
        name="gpt-5-mini",
        provider="openai",
        capability_tags=frozenset({"chat", "summarization", "classification", "fast"}),
        input_cost_per_1k_tokens_usd=0.001,
        output_cost_per_1k_tokens_usd=0.004,
        max_context_tokens=128_000,
        relative_speed_rank=1,
    ),
    ModelProfile(
        name="gpt-5",
        provider="openai",
        capability_tags=frozenset({"chat", "summarization", "classification", "reasoning", "code"}),
        input_cost_per_1k_tokens_usd=0.005,
        output_cost_per_1k_tokens_usd=0.02,
        max_context_tokens=128_000,
        relative_speed_rank=2,
    ),
    # --- Google ---
    ModelProfile(
        name="gemini-2.5-flash",
        provider="google",
        capability_tags=frozenset({"chat", "summarization", "classification", "fast"}),
        input_cost_per_1k_tokens_usd=0.0005,
        output_cost_per_1k_tokens_usd=0.003,
        max_context_tokens=1_000_000,
        relative_speed_rank=1,
    ),
    ModelProfile(
        name="gemini-2.5-pro",
        provider="google",
        capability_tags=frozenset({"chat", "summarization", "classification", "reasoning", "code", "deep-research"}),
        input_cost_per_1k_tokens_usd=0.0035,
        output_cost_per_1k_tokens_usd=0.014,
        max_context_tokens=1_000_000,
        relative_speed_rank=2,
    ),
]

KIMI_MODEL_PROFILE = ModelProfile(
    name="kimi-k3",
    provider="kimi",
    capability_tags=frozenset({"chat", "summarization", "classification", "reasoning", "code"}),
    input_cost_per_1k_tokens_usd=0.0,
    output_cost_per_1k_tokens_usd=0.0,
    max_context_tokens=256_000,
    relative_speed_rank=2,
)


def build_default_router(include_kimi: bool = False) -> ModelRouter:
    profiles = [*DEFAULT_MODEL_PROFILES]
    if include_kimi:
        profiles.append(KIMI_MODEL_PROFILE)
    return ModelRouter(profiles=profiles)
