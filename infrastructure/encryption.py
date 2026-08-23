# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
EncryptionService provides real Fernet encryption and decryption. Fernet combines
AES-128-CBC confidentiality with HMAC-SHA256 authentication and integrity, so a
tampered ciphertext fails decryption explicitly rather than returning silent
corruption.

This implementation lives exclusively in infrastructure. Domain and application
layers do not handle encryption; content remains ordinary text to them. Encryption
occurs only on actual database writes and reads in PostgresMemoryRepository.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class EncryptionKeyMissing(Exception):
    def __init__(self):
        super().__init__(
            "REUS_ENCRYPTION_KEY is not configured. It is required when REUS_STORAGE_BACKEND=postgres "
            "to encrypt memory content before storage. Generate a key with: "
            "python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )


class DecryptionFailed(Exception):
    def __init__(self):
        super().__init__("Decryption failed: the key is incorrect or ciphertext is corrupt or tampered with")


class EncryptionService:
    def __init__(self, key: str) -> None:
        if not key:
            raise EncryptionKeyMissing()
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "REUS_ENCRYPTION_KEY is invalid; it must be a base64-encoded 32-byte Fernet key"
            ) from exc

    def encrypt_text(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt_text(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as exc:
            raise DecryptionFailed() from exc
