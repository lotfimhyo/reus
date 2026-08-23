# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
secrets_resolver keeps config.py independent of heavier dependencies such as
hvac and boto3. This module is imported only when REUS_SECRETS_BACKEND is
explicitly enabled, not whenever config.py loads, following the same lazy-
construction approach as other optional provider clients.
"""
from __future__ import annotations

import logging

from infrastructure.secrets_provider import SecretsProvider

logger = logging.getLogger("reus_veritas.secrets")

# Only sensitive fields can be overridden by an external secrets provider.
# Non-sensitive operational fields such as worker_pool_size or storage_backend
# always remain sourced from environment configuration.
SECRET_FIELDS = [
    "api_key",
    "anthropic_api_key",
    "openai_api_key",
    "google_api_key",
    "telegram_bot_token",
    "encryption_key",
    "database_url",
]


def _build_provider(settings) -> SecretsProvider:
    if settings.secrets_backend == "vault":
        from infrastructure.vault_secrets_provider import VaultSecretsProvider

        return VaultSecretsProvider(
            vault_addr=settings.secrets_vault_addr,
            vault_token=settings.secrets_vault_token,
            secret_path=settings.secrets_vault_path,
        )
    if settings.secrets_backend == "aws":
        from infrastructure.aws_secrets_provider import AWSSecretsManagerProvider

        return AWSSecretsManagerProvider(
            region_name=settings.secrets_aws_region, secret_id=settings.secrets_aws_secret_id
        )
    raise ValueError(f"Unsupported secrets backend: '{settings.secrets_backend}'")


def resolve_secrets(settings):
    """Return a settings copy whose SECRET_FIELDS values are overridden by an
    external provider when available. Fields absent from the provider retain
    their environment or .env values, enabling deliberate partial overrides."""
    provider = _build_provider(settings)
    overrides: dict[str, str] = {}
    for field in SECRET_FIELDS:
        value = provider.get_secret(field)
        if value is not None:
            overrides[field] = value

    if not overrides:
        logger.warning(
            "no_secrets_resolved_from_external_provider",
            extra={"event_name": "no_secrets_resolved", "payload": {"backend": settings.secrets_backend}},
        )

    return settings.model_copy(update=overrides)
