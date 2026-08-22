"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Exceptions raised by the Identity & Security Layer.
"""


class VeritasIdentityError(Exception):
    """Base class for all errors raised by the identity layer."""


class UnknownComponentError(VeritasIdentityError):
    """Raised when a component_id is not found in the IdentityRegistry."""


class InvalidSignatureError(VeritasIdentityError):
    """Raised when a signature fails verification against a public key."""


class AuditChainCorruptedError(VeritasIdentityError):
    """Raised when the audit log's hash chain fails integrity verification."""
