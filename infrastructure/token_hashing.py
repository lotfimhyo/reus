# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
توليد رموز الوكلاء وتجزئتها. النص الصافي يُولَّد عشوائيًا بقوة تشفيرية (secrets)،
ولا يُخزَّن أبدًا — فقط SHA-256 الخاص به. هذا نفس مبدأ تخزين كلمات المرور: حتى لو
تسرّبت قاعدة البيانات بالكامل، لا يمكن استخراج الرموز الصافية منها.
"""
from __future__ import annotations

import hashlib
import secrets

_TOKEN_PREFIX = "rvos_"  # يسمح بتمييز رموز هذا النظام بصريًا (مثل أنماط Stripe/GitHub)


def generate_plaintext_token() -> str:
    return f"{_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
