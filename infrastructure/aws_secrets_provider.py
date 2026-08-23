# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
AWSSecretsManagerProvider uses boto3 with AWS Secrets Manager. It reads a
single secret_id whose JSON fields contain the configured secrets.

The provider is verified through an injected boto3 test double. This
development environment does not establish live network access to AWS services,
so the implementation does not claim live AWS validation here.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from infrastructure.secrets_provider import SecretsProvider

logger = logging.getLogger("reus_veritas.secrets.aws")


class AWSSecretsManagerProvider(SecretsProvider):
    def __init__(self, region_name: str, secret_id: str, client: Any = None) -> None:
        self._region_name = region_name
        self._secret_id = secret_id
        self._injected_client = client
        self._client: Any = None  # Lazy construction keeps this dependency optional.
        self._cache: dict[str, str] | None = None

    def _get_client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        if self._client is None:
            import boto3

            self._client = boto3.client("secretsmanager", region_name=self._region_name)
        return self._client

    def _load_secrets(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        try:
            response = self._get_client().get_secret_value(SecretId=self._secret_id)
            self._cache = json.loads(response["SecretString"])
        except Exception:
            logger.exception("aws_secrets_read_failed", extra={"event_name": "aws_secrets_read_failed"})
            self._cache = {}
        return self._cache

    def get_secret(self, key: str) -> str | None:
        return self._load_secrets().get(key)
