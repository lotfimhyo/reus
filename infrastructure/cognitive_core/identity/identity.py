"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

ComponentIdentity: the cryptographic identity every component in Veritas AI
(a layer, an agent, a tool) must hold, per the master architecture doc
section 5: "هوية تشفيرية لكل مكون".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from infrastructure.cognitive_core.identity.keys import KeyPair, generate_keypair, keypair_from_private_hex


@dataclass(frozen=True)
class IdentityManifest:
    """
    The *public* record of a component's identity — safe to share, store in
    the registry, and embed in audit log entries. Never contains key material.
    """

    component_id: str
    component_type: str
    public_key_hex: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "component_type": self.component_type,
            "public_key_hex": self.public_key_hex,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "IdentityManifest":
        return IdentityManifest(
            component_id=data["component_id"],
            component_type=data["component_type"],
            public_key_hex=data["public_key_hex"],
            created_at=data["created_at"],
        )


@dataclass
class ComponentIdentity:
    """
    The *private* handle to a component's identity, held only by the
    component itself. Wraps a KeyPair and exposes signing, but never
    exposes the raw private key outside this object.
    """

    component_type: str
    _keypair: KeyPair = field(repr=False)
    component_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def create(cls, component_type: str) -> "ComponentIdentity":
        """Create a brand-new identity with a freshly generated key pair."""
        if not component_type or not component_type.strip():
            raise ValueError("component_type must be a non-empty string.")
        return cls(component_type=component_type, _keypair=generate_keypair())

    @classmethod
    def from_persisted(
        cls,
        component_id: str,
        component_type: str,
        private_key_hex: str,
        created_at: str,
    ) -> "ComponentIdentity":
        """
        Reconstruct a previously-created identity from its exported private
        key — used only for identities that must survive a process
        restart (currently: a device's own cluster node identity; see
        cluster/node_identity.py). Every other identity in this project is
        deliberately re-created fresh each run.
        """
        return cls(
            component_type=component_type,
            _keypair=keypair_from_private_hex(private_key_hex),
            component_id=component_id,
            created_at=created_at,
        )

    def export_private_key_hex(self) -> str:
        """
        Export this identity's private key as hex, for persistence by a
        caller that explicitly needs cross-restart identity (see
        from_persisted() above). Deliberately named loudly rather than
        exposed as a property — this is secret material, and every call
        site should read as an obvious, intentional decision to persist it.
        """
        return self._keypair.private_key_hex

    @property
    def public_key_hex(self) -> str:
        return self._keypair.public_key_hex

    def manifest(self) -> IdentityManifest:
        """Export the public, shareable manifest for this identity."""
        return IdentityManifest(
            component_id=self.component_id,
            component_type=self.component_type,
            public_key_hex=self.public_key_hex,
            created_at=self.created_at,
        )

    def sign(self, payload: bytes) -> bytes:
        """Sign a payload on behalf of this component."""
        return self._keypair.sign(payload)
