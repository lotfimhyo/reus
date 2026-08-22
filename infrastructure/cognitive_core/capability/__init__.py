"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Layer 4 — Capability Registry.

Public surface: other layers must depend only on the symbols exported here.
"""

from infrastructure.cognitive_core.capability.capability_layer import CapabilityLayer
from infrastructure.cognitive_core.capability.descriptor import CapabilityDescriptor, RiskLevel
from infrastructure.cognitive_core.capability.exceptions import (
    InvalidDescriptorError,
    UnknownCapabilityError,
    VeritasCapabilityError,
)
from infrastructure.cognitive_core.capability.registry import CapabilityRegistry

__all__ = [
    "CapabilityLayer",
    "CapabilityRegistry",
    "CapabilityDescriptor",
    "RiskLevel",
    "VeritasCapabilityError",
    "UnknownCapabilityError",
    "InvalidDescriptorError",
]
