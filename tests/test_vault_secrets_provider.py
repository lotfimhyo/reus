# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
VaultSecretsProvider tests using an injected fake hvac client.
"""
from __future__ import annotations

from infrastructure.vault_secrets_provider import VaultSecretsProvider


class _FakeKV2:
    def __init__(self, data: dict) -> None:
        self._data = data
        self.read_calls = 0

    def read_secret_version(self, path: str):
        self.read_calls += 1
        return {"data": {"data": self._data}}


class _FakeVaultClient:
    def __init__(self, data: dict) -> None:
        self.secrets = type("Secrets", (), {"kv": type("KV", (), {"v2": _FakeKV2(data)})()})()


def test_get_secret_returns_value_from_vault():
    client = _FakeVaultClient({"anthropic_api_key": "sk-vault-123"})
    provider = VaultSecretsProvider(vault_addr="http://vault", vault_token="t", secret_path="p", client=client)

    assert provider.get_secret("anthropic_api_key") == "sk-vault-123"


def test_get_secret_returns_none_for_missing_key():
    client = _FakeVaultClient({"anthropic_api_key": "sk-vault-123"})
    provider = VaultSecretsProvider(vault_addr="http://vault", vault_token="t", secret_path="p", client=client)

    assert provider.get_secret("does_not_exist") is None


def test_secrets_are_cached_after_first_read():
    client = _FakeVaultClient({"api_key": "x"})
    provider = VaultSecretsProvider(vault_addr="http://vault", vault_token="t", secret_path="p", client=client)

    provider.get_secret("api_key")
    provider.get_secret("api_key")

    assert client.secrets.kv.v2.read_calls == 1


def test_vault_read_failure_returns_none_instead_of_raising():
    class _FailingClient:
        pass

    provider = VaultSecretsProvider(
        vault_addr="http://vault", vault_token="t", secret_path="p", client=_FailingClient()
    )

    assert provider.get_secret("anything") is None
