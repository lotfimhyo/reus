# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
SecretsProvider separates the origin of a secret from the rest of the system.
The default EnvSecretsProvider preserves current behavior by reading environment
variables and .env through pydantic-settings; nothing changes unless
REUS_SECRETS_BACKEND is explicitly enabled. Vault and AWS implementations live
in separate modules so their heavier dependencies remain genuinely optional.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod


class SecretNotFound(Exception):
    def __init__(self, key: str, backend: str):
        super().__init__(f"Secret '{key}' was not found in secrets backend '{backend}'")


class SecretsProvider(ABC):
    @abstractmethod
    def get_secret(self, key: str) -> str | None:
        """Return a secret value or None when absent; absence is a normal state, not an exception."""
        ...


class EnvSecretsProvider(SecretsProvider):
    """Default implementation: read directly from environment variables (REUS_<KEY_UPPER>)."""

    def __init__(self, prefix: str = "REUS_") -> None:
        self._prefix = prefix

    def get_secret(self, key: str) -> str | None:
        return os.environ.get(f"{self._prefix}{key.upper()}")
