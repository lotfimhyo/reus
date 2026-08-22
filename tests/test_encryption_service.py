# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest
from cryptography.fernet import Fernet

from infrastructure.encryption import DecryptionFailed, EncryptionKeyMissing, EncryptionService

VALID_KEY = Fernet.generate_key().decode()
OTHER_KEY = Fernet.generate_key().decode()


def test_missing_key_raises():
    with pytest.raises(EncryptionKeyMissing):
        EncryptionService(key="")


def test_invalid_key_format_raises():
    with pytest.raises(ValueError):
        EncryptionService(key="not-a-valid-fernet-key")


def test_encrypt_then_decrypt_round_trip():
    service = EncryptionService(key=VALID_KEY)
    ciphertext = service.encrypt_text("محتوى حساس جدًا")

    assert service.decrypt_text(ciphertext) == "محتوى حساس جدًا"


def test_ciphertext_does_not_contain_plaintext():
    service = EncryptionService(key=VALID_KEY)
    plaintext = "رقم سري: 123456"

    ciphertext = service.encrypt_text(plaintext)

    assert plaintext.encode("utf-8") not in ciphertext
    assert b"123456" not in ciphertext


def test_decrypt_with_wrong_key_fails_loudly():
    encrypted_with_key_a = EncryptionService(key=VALID_KEY).encrypt_text("سر")
    service_with_key_b = EncryptionService(key=OTHER_KEY)

    with pytest.raises(DecryptionFailed):
        service_with_key_b.decrypt_text(encrypted_with_key_a)


def test_decrypt_tampered_ciphertext_fails_loudly():
    service = EncryptionService(key=VALID_KEY)
    ciphertext = bytearray(service.encrypt_text("بيانات أصلية"))
    ciphertext[-1] ^= 0xFF  # تلاعب بآخر بايت

    with pytest.raises(DecryptionFailed):
        service.decrypt_text(bytes(ciphertext))


def test_same_plaintext_produces_different_ciphertext_each_time():
    """Fernet يضيف IV عشوائيًا؛ نفس النص يجب ألا يُنتج نفس الشفرة مرتين (يمنع تحليل الأنماط)."""
    service = EncryptionService(key=VALID_KEY)
    c1 = service.encrypt_text("نفس النص")
    c2 = service.encrypt_text("نفس النص")

    assert c1 != c2
    assert service.decrypt_text(c1) == service.decrypt_text(c2) == "نفس النص"
