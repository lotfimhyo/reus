# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
EncryptionService: تشفير/فك تشفير حقيقي عبر Fernet (مواصفة قياسية تجمع
AES-128-CBC للسرية و HMAC-SHA256 للمصادقة/سلامة البيانات — أي تلاعب بالنص
المشفّر يجعل فك التشفير يفشل بوضوح بدل إرجاع بيانات فاسدة صامتة).

هذه الطبقة تعمل حصرًا في infrastructure/: طبقتا domain وapplication لا تعرفان
شيئًا عن التشفير إطلاقًا (المحتوى يظل نصًا عاديًا بالنسبة لهما دائمًا)، والتشفير
يحدث فقط عند الكتابة/القراءة الفعلية من قاعدة البيانات في PostgresMemoryRepository.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class EncryptionKeyMissing(Exception):
    def __init__(self):
        super().__init__(
            "REUS_ENCRYPTION_KEY غير مضبوط. مطلوب إلزاميًا عند استخدام REUS_STORAGE_BACKEND=postgres "
            "لتشفير محتوى الذاكرة قبل تخزينه. ولّد مفتاحًا عبر: "
            "python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )


class DecryptionFailed(Exception):
    def __init__(self):
        super().__init__("فشل فك التشفير: المفتاح غير صحيح أو البيانات المشفّرة تالفة/مُتلاعَب بها")


class EncryptionService:
    def __init__(self, key: str) -> None:
        if not key:
            raise EncryptionKeyMissing()
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "REUS_ENCRYPTION_KEY غير صالح؛ يجب أن يكون مفتاح Fernet بترميز base64 (32 بايت)"
            ) from exc

    def encrypt_text(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt_text(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as exc:
            raise DecryptionFailed() from exc
