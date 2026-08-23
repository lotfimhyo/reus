# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Agent-token generation and hashing. Plaintext tokens are generated with
cryptographic randomness (`secrets`) and are never stored; only their SHA-256
hash is retained. As with password storage, a database leak cannot recover the
plaintext tokens from those hashes.
"""
from __future__ import annotations

import hashlib
import secrets

_TOKEN_PREFIX = "rvos_"  # Makes this system's tokens visually identifiable.


def generate_plaintext_token() -> str:
    return f"{_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
