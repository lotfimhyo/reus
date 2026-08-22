"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Cryptographic primitives for the Identity & Security Layer.

Design decision (documented per the master architecture doc, section 4):
Ed25519 was chosen over RSA for smaller keys and faster sign/verify,
which matters because every inter-layer call is signed and audited.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from infrastructure.cognitive_core.identity.exceptions import InvalidSignatureError


@dataclass(frozen=True)
class KeyPair:
    """An Ed25519 key pair. The private key never leaves the owning process."""

    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey

    @property
    def public_key_hex(self) -> str:
        raw = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return raw.hex()

    @property
    def private_key_hex(self) -> str:
        """Export the raw private key as hex — only ever used for
        persisting a device's own long-lived node identity to local disk
        (see cluster/node_identity.py). Never transmitted over any
        network; only cluster_secret.py's HMAC proof leaves this process."""
        raw = self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return raw.hex()

    def sign(self, payload: bytes) -> bytes:
        """Sign arbitrary bytes with the private key."""
        return self.private_key.sign(payload)


def generate_keypair() -> KeyPair:
    """Generate a fresh Ed25519 key pair for a new component identity."""
    private_key = Ed25519PrivateKey.generate()
    return KeyPair(private_key=private_key, public_key=private_key.public_key())


def public_key_from_hex(public_key_hex: str) -> Ed25519PublicKey:
    """Reconstruct a public key object from its hex-encoded raw bytes."""
    raw = bytes.fromhex(public_key_hex)
    return Ed25519PublicKey.from_public_bytes(raw)


def keypair_from_private_hex(private_key_hex: str) -> KeyPair:
    """
    Reconstruct a full KeyPair from a previously-exported private key.

    Added for the cluster layer's node identity (Hybrid Mode architecture
    doc, section 3.1): unlike every other ComponentIdentity in this
    project (created fresh per-process, e.g. for CognitiveEngine's or
    LearningLayer's internal actor identity), a device's own node identity
    must stay the same across restarts so peers keep recognizing it as the
    same device rather than treating every restart as a brand-new node.
    """
    raw = bytes.fromhex(private_key_hex)
    private_key = Ed25519PrivateKey.from_private_bytes(raw)
    return KeyPair(private_key=private_key, public_key=private_key.public_key())


def verify(public_key_hex: str, payload: bytes, signature: bytes) -> None:
    """
    Verify a signature against a hex-encoded public key.

    Raises InvalidSignatureError if verification fails, instead of returning
    a bare boolean, so that callers cannot accidentally ignore a failed check.
    """
    public_key = public_key_from_hex(public_key_hex)
    try:
        public_key.verify(signature, payload)
    except InvalidSignature as exc:
        raise InvalidSignatureError(
            "Signature verification failed for the given public key."
        ) from exc


def is_valid(public_key_hex: str, payload: bytes, signature: bytes) -> bool:
    """Boolean convenience wrapper around verify()."""
    try:
        verify(public_key_hex, payload, signature)
        return True
    except InvalidSignatureError:
        return False
