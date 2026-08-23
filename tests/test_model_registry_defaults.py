# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from application.model_router import TaskRequirements
from infrastructure.model_registry import DEFAULT_MODEL_PROFILES, build_default_router


def test_default_registry_includes_multiple_providers():
    providers = {m.provider for m in DEFAULT_MODEL_PROFILES}
    assert providers == {"anthropic", "openai", "google"}


def test_default_registry_has_at_least_one_model_per_provider():
    router = build_default_router()
    for provider in ("anthropic", "openai", "google"):
        models = [m for m in router.list_profiles() if m.provider == provider]
        assert len(models) >= 1, f"No model is registered for provider {provider}"


def test_router_can_select_cheapest_across_all_providers():
    router = build_default_router()
    cheapest = router.select(TaskRequirements(prefer="cheapest"))
    all_costs = [m.input_cost_per_1k_tokens_usd for m in router.list_profiles()]
    assert cheapest.input_cost_per_1k_tokens_usd == min(all_costs)


def test_router_can_select_most_capable_across_all_providers():
    router = build_default_router()
    most_capable = router.select(
        TaskRequirements(required_capabilities=frozenset({"deep-research"}), prefer="most_capable")
    )
    assert "deep-research" in most_capable.capability_tags
