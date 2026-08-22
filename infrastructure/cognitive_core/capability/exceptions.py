"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Exceptions raised by the Capability Layer.
"""


class VeritasCapabilityError(Exception):
    """Base class for all errors raised by the capability layer."""


class UnknownCapabilityError(VeritasCapabilityError):
    """Raised when looking up a capability_id that is not registered."""


class InvalidDescriptorError(VeritasCapabilityError):
    """Raised when a capability descriptor fails validation (e.g. missing
    a required field, or an out-of-range risk_level/cost)."""
