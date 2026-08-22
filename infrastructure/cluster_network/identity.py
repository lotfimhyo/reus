# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
NodeIdentity: the cryptographic identity of a node, per the architecture
doc's Communication & Trust Layer ("each node has a fixed cryptographic
identifier ... Ed25519 keypair").

Two separate keypairs are kept, deliberately:
  - An Ed25519 keypair signs message *payloads*, so integrity holds even
    if the transport layer were somehow compromised.
  - An RSA keypair + self-signed cert secures the *transport* itself
    (mutual TLS) via `secure_server.py` / `secure_client.py`.

Everything persists under `<base_dir>/<node_id>/`, generated once and
reused on subsequent runs.
"""

import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from infrastructure.cluster_network.certs import generate_self_signed_cert


class NodeIdentity:
    def __init__(self, node_id: str, base_dir: str = "./phoenix_network"):
        self.node_id = node_id
        self.dir = os.path.join(base_dir, node_id)
        os.makedirs(self.dir, exist_ok=True)

        self.cert_path = os.path.join(self.dir, "cert.pem")
        self.tls_key_path = os.path.join(self.dir, "tls_key.pem")
        self._signing_key_path = os.path.join(self.dir, "signing_key.raw")
        self._signing_pub_path = os.path.join(self.dir, "signing_pub.raw")

        self._ensure_tls_cert()
        self._signing_key = self._load_or_create_signing_key()

    # -- TLS identity ------------------------------------------------------

    def _ensure_tls_cert(self) -> None:
        if os.path.exists(self.cert_path) and os.path.exists(self.tls_key_path):
            return
        cert_pem, key_pem = generate_self_signed_cert(self.node_id)
        with open(self.cert_path, "wb") as f:
            f.write(cert_pem)
        with open(self.tls_key_path, "wb") as f:
            f.write(key_pem)

    # -- Signing identity ----------------------------------------------------

    def _load_or_create_signing_key(self) -> Ed25519PrivateKey:
        if os.path.exists(self._signing_key_path):
            with open(self._signing_key_path, "rb") as f:
                raw = f.read()
            return Ed25519PrivateKey.from_private_bytes(raw)

        key = Ed25519PrivateKey.generate()
        raw_priv = key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        raw_pub = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        with open(self._signing_key_path, "wb") as f:
            f.write(raw_priv)
        with open(self._signing_pub_path, "wb") as f:
            f.write(raw_pub)
        return key

    @property
    def cert_pem(self) -> str:
        with open(self.cert_path, "r", encoding="utf-8") as f:
            return f.read()

    @property
    def signing_public_key_hex(self) -> str:
        raw_pub = self._signing_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return raw_pub.hex()

    def sign(self, payload: bytes) -> str:
        return self._signing_key.sign(payload).hex()

    @staticmethod
    def verify(signing_pubkey_hex: str, payload: bytes, signature_hex: str) -> bool:
        try:
            pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(signing_pubkey_hex))
            pubkey.verify(bytes.fromhex(signature_hex), payload)
            return True
        except Exception:
            return False
