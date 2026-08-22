# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
SecretsProvider: يفصل "من أين يأتي السرّ فعليًا" عن بقية النظام. التطبيق
الافتراضي (EnvSecretsProvider) يحافظ على السلوك الحالي تمامًا (قراءة من
متغيرات البيئة/.env عبر pydantic-settings) — لا يتغير شيء إن لم يُفعَّل
REUS_SECRETS_BACKEND صراحة. التطبيقات الأخرى (Vault, AWS) في ملفات منفصلة
حتى تبقى اعتمادياتها الثقيلة (hvac, boto3) اختيارية فعليًا.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod


class SecretNotFound(Exception):
    def __init__(self, key: str, backend: str):
        super().__init__(f"لم يُعثر على السرّ '{key}' في مزوّد الأسرار '{backend}'")


class SecretsProvider(ABC):
    @abstractmethod
    def get_secret(self, key: str) -> str | None:
        """يُعيد قيمة السرّ، أو None إن لم يكن موجودًا (وليس استثناءً؛ الغياب حالة طبيعية)."""
        ...


class EnvSecretsProvider(SecretsProvider):
    """التطبيق الافتراضي: يقرأ من متغيرات البيئة مباشرة (REUS_<KEY_UPPER>)."""

    def __init__(self, prefix: str = "REUS_") -> None:
        self._prefix = prefix

    def get_secret(self, key: str) -> str | None:
        return os.environ.get(f"{self._prefix}{key.upper()}")
