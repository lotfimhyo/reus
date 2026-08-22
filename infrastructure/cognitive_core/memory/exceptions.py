"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Exceptions raised by the Memory Layer.
"""


class VeritasMemoryError(Exception):
    """Base class for all errors raised by the memory layer."""


class UnknownSessionError(VeritasMemoryError):
    """Raised when a Working Memory operation targets a session_id that
    was never created (or was already cleared)."""


class UnknownEpisodeError(VeritasMemoryError):
    """Raised when looking up an episodic memory record that does not exist."""


class UnknownEntityError(VeritasMemoryError):
    """Raised when a semantic memory operation references an entity that
    has not been registered."""
