# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from infrastructure.secrets_provider import EnvSecretsProvider
from infrastructure.secrets_resolver import resolve_secrets


def test_env_secrets_provider_reads_prefixed_env_var(monkeypatch):
    monkeypatch.setenv("REUS_ANTHROPIC_API_KEY", "sk-env-789")
    provider = EnvSecretsProvider()

    assert provider.get_secret("anthropic_api_key") == "sk-env-789"


def test_env_secrets_provider_returns_none_for_missing(monkeypatch):
    monkeypatch.delenv("REUS_SOME_UNSET_KEY", raising=False)
    provider = EnvSecretsProvider()

    assert provider.get_secret("some_unset_key") is None


def test_resolve_secrets_overrides_only_fields_found_in_provider():
    from config import Settings

    class _FakeProvider:
        def get_secret(self, key: str) -> str | None:
            return "resolved-value" if key == "anthropic_api_key" else None

    settings = Settings(anthropic_api_key="original", openai_api_key="original-openai")

    import infrastructure.secrets_resolver as resolver_module

    original_build = resolver_module._build_provider
    resolver_module._build_provider = lambda s: _FakeProvider()
    try:
        resolved = resolve_secrets(settings)
    finally:
        resolver_module._build_provider = original_build

    assert resolved.anthropic_api_key == "resolved-value"
    assert resolved.openai_api_key == "original-openai"  # Not found in the provider, so it remains unchanged.


def test_resolve_secrets_raises_for_unsupported_backend():
    from config import Settings

    settings = Settings(secrets_backend="unsupported-backend")
    with pytest.raises(ValueError):
        resolve_secrets(settings)


def test_resolve_secrets_with_real_vault_provider_via_injected_client():
    from config import Settings

    settings = Settings(secrets_backend="vault", secrets_vault_path="reus-veritas")

    import infrastructure.secrets_resolver as resolver_module
    from infrastructure.vault_secrets_provider import VaultSecretsProvider

    class _FakeKV2:
        def read_secret_version(self, path: str):
            return {"data": {"data": {"api_key": "vault-master-key"}}}

    class _FakeVaultClient:
        secrets = type("S", (), {"kv": type("K", (), {"v2": _FakeKV2()})()})()

    original_build = resolver_module._build_provider
    resolver_module._build_provider = lambda s: VaultSecretsProvider(
        vault_addr="http://vault", vault_token="t", secret_path="p", client=_FakeVaultClient()
    )
    try:
        resolved = resolve_secrets(settings)
    finally:
        resolver_module._build_provider = original_build

    assert resolved.api_key == "vault-master-key"
