# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from application.model_router import ModelProfile, ModelRouter, NoSuitableModel, TaskRequirements

CHEAP_FAST = ModelProfile(
    name="cheap-fast",
    provider="test",
    capability_tags=frozenset({"chat"}),
    input_cost_per_1k_tokens_usd=0.001,
    output_cost_per_1k_tokens_usd=0.002,
    max_context_tokens=8_000,
    relative_speed_rank=1,
)
BALANCED = ModelProfile(
    name="balanced",
    provider="test",
    capability_tags=frozenset({"chat", "reasoning", "code"}),
    input_cost_per_1k_tokens_usd=0.003,
    output_cost_per_1k_tokens_usd=0.015,
    max_context_tokens=200_000,
    relative_speed_rank=2,
)
EXPENSIVE_CAPABLE = ModelProfile(
    name="expensive-capable",
    provider="test",
    capability_tags=frozenset({"chat", "reasoning", "code", "deep-research"}),
    input_cost_per_1k_tokens_usd=0.015,
    output_cost_per_1k_tokens_usd=0.075,
    max_context_tokens=200_000,
    relative_speed_rank=3,
)


@pytest.fixture
def router() -> ModelRouter:
    return ModelRouter(profiles=[CHEAP_FAST, BALANCED, EXPENSIVE_CAPABLE])


def test_router_requires_at_least_one_profile():
    with pytest.raises(ValueError):
        ModelRouter(profiles=[])


def test_selects_cheapest_by_default(router: ModelRouter):
    model = router.select(TaskRequirements())
    assert model.name == "cheap-fast"


def test_filters_by_required_capability(router: ModelRouter):
    model = router.select(TaskRequirements(required_capabilities=frozenset({"reasoning"})))
    assert model.name == "balanced"  # The cheapest model that supports reasoning.


def test_no_suitable_model_for_unknown_capability(router: ModelRouter):
    with pytest.raises(NoSuitableModel):
        router.select(TaskRequirements(required_capabilities=frozenset({"vision"})))


def test_filters_by_min_context_tokens(router: ModelRouter):
    model = router.select(TaskRequirements(min_context_tokens=50_000))
    assert model.name in {"balanced", "expensive-capable"}
    assert model.max_context_tokens >= 50_000


def test_no_suitable_model_when_context_too_large(router: ModelRouter):
    with pytest.raises(NoSuitableModel):
        router.select(TaskRequirements(min_context_tokens=1_000_000))


def test_filters_by_max_cost(router: ModelRouter):
    model = router.select(
        TaskRequirements(required_capabilities=frozenset({"reasoning"}), max_input_cost_per_1k_tokens_usd=0.003)
    )
    assert model.name == "balanced"

    with pytest.raises(NoSuitableModel):
        router.select(
            TaskRequirements(
                required_capabilities=frozenset({"deep-research"}), max_input_cost_per_1k_tokens_usd=0.002
            )
        )


def test_prefer_fastest(router: ModelRouter):
    model = router.select(TaskRequirements(required_capabilities=frozenset({"reasoning"}), prefer="fastest"))
    assert model.name == "balanced"  # The fastest model that supports reasoning (lower rank).


def test_prefer_most_capable(router: ModelRouter):
    model = router.select(TaskRequirements(prefer="most_capable"))
    assert model.name == "expensive-capable"


def test_list_profiles_returns_all(router: ModelRouter):
    assert len(router.list_profiles()) == 3
