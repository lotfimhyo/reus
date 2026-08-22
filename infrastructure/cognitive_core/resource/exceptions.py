"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Exceptions raised by the Resource & Execution Layer (Layer 2).
"""


class VeritasResourceError(Exception):
    """Base class for all errors raised by the resource & execution layer."""


class SchedulerShutDownError(VeritasResourceError):
    """Raised when submit() is called on a TaskScheduler that has already
    been shut down."""
