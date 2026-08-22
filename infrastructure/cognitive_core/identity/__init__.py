"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Layer 1 — Identity & Security Layer.

Public surface of this layer. Other layers (Resource, Memory, Capability,
Cognitive Engine, Interface) must only depend on the symbols exported here,
never on internal module paths — this preserves the "no leaky abstractions"
rule from the master architecture document.
"""

from infrastructure.cognitive_core.identity.audit_log import AppendOnlyAuditLog, AuditEntry
from infrastructure.cognitive_core.identity.exceptions import (
    AuditChainCorruptedError,
    InvalidSignatureError,
    UnknownComponentError,
    VeritasIdentityError,
)
from infrastructure.cognitive_core.identity.identity import ComponentIdentity, IdentityManifest
from infrastructure.cognitive_core.identity.registry import IdentityRegistry

__all__ = [
    "ComponentIdentity",
    "IdentityManifest",
    "AppendOnlyAuditLog",
    "AuditEntry",
    "IdentityRegistry",
    "VeritasIdentityError",
    "UnknownComponentError",
    "InvalidSignatureError",
    "AuditChainCorruptedError",
]
