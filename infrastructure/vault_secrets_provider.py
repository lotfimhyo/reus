# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
VaultSecretsProvider uses the official hvac SDK with HashiCorp Vault KV v2.
All secrets are read from one secret_path as fields on the same secret object,
which is the standard Vault pattern.

The provider is verified through an injected hvac test double. This development
environment does not establish live network access to an external Vault server,
so the implementation does not claim live Vault validation here.
"""
from __future__ import annotations

import logging
from typing import Any

from infrastructure.secrets_provider import SecretsProvider

logger = logging.getLogger("reus_veritas.secrets.vault")


class VaultSecretsProvider(SecretsProvider):
    def __init__(self, vault_addr: str, vault_token: str, secret_path: str, client: Any = None) -> None:
        self._secret_path = secret_path
        self._injected_client = client
        self._vault_addr = vault_addr
        self._vault_token = vault_token
        self._client: Any = None  # Lazy construction keeps this optional client isolated.
        self._cache: dict[str, str] | None = None

    def _get_client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        if self._client is None:
            import hvac

            self._client = hvac.Client(url=self._vault_addr, token=self._vault_token)
        return self._client

    def _load_secrets(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        try:
            response = self._get_client().secrets.kv.v2.read_secret_version(path=self._secret_path)
            self._cache = response["data"]["data"]
        except Exception:
            logger.exception("vault_read_failed", extra={"event_name": "vault_read_failed"})
            self._cache = {}
        return self._cache

    def get_secret(self, key: str) -> str | None:
        return self._load_secrets().get(key)
