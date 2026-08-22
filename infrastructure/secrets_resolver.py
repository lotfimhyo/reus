# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
secrets_resolver: يفصل config.py عن أي اعتمادية ثقيلة (hvac, boto3) — هذه
الوحدة تُستورد فقط عند تفعيل REUS_SECRETS_BACKEND صراحة، وليس عند كل استيراد
لـ config.py (نفس درس البناء الكسول من عملاء OpenAI/Google/Vault/AWS سابقًا).
"""
from __future__ import annotations

import logging

from infrastructure.secrets_provider import SecretsProvider

logger = logging.getLogger("reus_veritas.secrets")

# الحقول الحساسة الوحيدة القابلة للاستبدال من مزوّد أسرار خارجي. أي حقل تشغيلي
# غير حساس (مثل worker_pool_size أو storage_backend) يبقى دائمًا من متغيرات البيئة.
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
    raise ValueError(f"مزوّد أسرار غير مدعوم: '{settings.secrets_backend}'")


def resolve_secrets(settings):
    """
    يُعيد نسخة من settings بعد استبدال كل حقل في SECRET_FIELDS بقيمته من مزوّد
    الأسرار الخارجي إن وُجدت. الحقول غير الموجودة في المزوّد تبقى بقيمتها الأصلية
    (من متغيرات البيئة/.env) — لا صمت كامل ولا فشل كامل، استبدال جزئي معقول.
    """
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
