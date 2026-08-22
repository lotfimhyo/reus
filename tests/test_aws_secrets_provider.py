# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
اختبارات AWSSecretsManagerProvider عبر حقن عميل boto3 وهمي.
"""
from __future__ import annotations

import json

from infrastructure.aws_secrets_provider import AWSSecretsManagerProvider


class _FakeBoto3Client:
    def __init__(self, secret_dict: dict) -> None:
        self._secret_dict = secret_dict
        self.calls = 0

    def get_secret_value(self, SecretId: str):
        self.calls += 1
        return {"SecretString": json.dumps(self._secret_dict)}


def test_get_secret_returns_value_from_aws():
    client = _FakeBoto3Client({"anthropic_api_key": "sk-aws-456"})
    provider = AWSSecretsManagerProvider(region_name="us-east-1", secret_id="reus-veritas/prod", client=client)

    assert provider.get_secret("anthropic_api_key") == "sk-aws-456"


def test_get_secret_returns_none_for_missing_key():
    client = _FakeBoto3Client({"anthropic_api_key": "sk-aws-456"})
    provider = AWSSecretsManagerProvider(region_name="us-east-1", secret_id="reus-veritas/prod", client=client)

    assert provider.get_secret("does_not_exist") is None


def test_secrets_are_cached_after_first_read():
    client = _FakeBoto3Client({"api_key": "x"})
    provider = AWSSecretsManagerProvider(region_name="us-east-1", secret_id="reus-veritas/prod", client=client)

    provider.get_secret("api_key")
    provider.get_secret("api_key")

    assert client.calls == 1


def test_aws_read_failure_returns_none_instead_of_raising():
    class _FailingClient:
        pass

    provider = AWSSecretsManagerProvider(region_name="us-east-1", secret_id="p", client=_FailingClient())

    assert provider.get_secret("anything") is None
