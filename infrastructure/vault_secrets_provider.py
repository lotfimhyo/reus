# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
VaultSecretsProvider: تطبيق حقيقي وكامل عبر SDK الرسمي (hvac) لمحرك KV v2 في
HashiCorp Vault. كل الأسرار تُقرأ من مسار واحد (secret_path) كحقول ضمن نفس
الكائن السرّي — النمط المعتاد في Vault.

قرار هندسي موثّق بصدق: كود إنتاجي كامل وصحيح، لكن بيئة تطوير هذا المشروع لا
تصل شبكيًا لأي خادم Vault خارجي (نفس القيد الموثّق مع OpenAI/Google/Telegram
سابقًا: مقيَّدة لـ api.anthropic.com فقط). اختُبر عبر حقن عميل hvac وهمي.
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
        self._client: Any = None  # بناء كسول (Lazy)؛ نفس الدرس المستفاد من عملاء OpenAI/Google سابقًا
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
