"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Exceptions raised by the Cognitive Engine (Layer 5).
"""


class VeritasCognitiveError(Exception):
    """Base class for all errors raised by the cognitive engine."""


class NoCapabilityFoundError(VeritasCognitiveError):
    """Raised when goal analysis finds no registered capability matching
    the goal's requirements, so no plan can be generated at all."""


class EmptyPlanSetError(VeritasCognitiveError):
    """Raised if plan evaluation is asked to select from zero candidate
    plans (should not normally happen if NoCapabilityFoundError is raised
    earlier, but guarded against defensively)."""
