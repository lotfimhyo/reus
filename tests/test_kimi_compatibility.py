"""Project: Reus | Developer: lotfi Mahiddine | Organization: Reulink."""

import pytest
from pydantic import ValidationError

from config import Settings
from infrastructure.model_client import KimiModelClient
from infrastructure.model_registry import build_default_router


def test_kimi_is_not_routable_without_explicit_enablement():
    assert all(profile.provider != "kimi" for profile in build_default_router()._profiles)
    assert any(profile.provider == "kimi" for profile in build_default_router(include_kimi=True)._profiles)


def test_kimi_requires_key_when_enabled():
    with pytest.raises(ValidationError, match="Kimi requires"):
        Settings(kimi_enabled=True)


def test_kimi_uses_openai_compatible_completion_contract():
    response = type("Response", (), {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "ok"})()})()]})()
    client = type("Client", (), {"chat": type("Chat", (), {"completions": type("Completions", (), {"create": lambda *_args, **_kwargs: response})()})()})()
    assert KimiModelClient("key", "https://api.moonshot.ai/v1", client=client).invoke("kimi-k3", "hello") == "ok"
