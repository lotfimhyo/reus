"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Exceptions raised by the Cognitive Engine's learning components (self-review,
knowledge extraction, and reliability-based plan adjustment).
"""


class VeritasLearningError(Exception):
    """Base class for all errors raised by the learning components."""
