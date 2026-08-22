# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from infrastructure.model_client import ModelClient
from infrastructure.model_client_registry import ModelClientRegistry, UnknownProvider


class _DummyClient(ModelClient):
    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        return "dummy"


def test_get_registered_provider_returns_client():
    client = _DummyClient()
    registry = ModelClientRegistry({"anthropic": client})
    assert registry.get("anthropic") is client


def test_get_unknown_provider_raises():
    registry = ModelClientRegistry({"anthropic": _DummyClient()})
    with pytest.raises(UnknownProvider):
        registry.get("openai")


def test_register_adds_provider_dynamically():
    registry = ModelClientRegistry()
    client = _DummyClient()
    registry.register("google", client)
    assert registry.get("google") is client


def test_providers_lists_all_registered():
    registry = ModelClientRegistry({"anthropic": _DummyClient(), "openai": _DummyClient()})
    assert set(registry.providers()) == {"anthropic", "openai"}
