"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Exceptions raised by the cluster discovery/join components (Hybrid/Cloud
Mode architecture doc, section 3).
"""


class VeritasClusterError(Exception):
    """Base class for all errors raised by the cluster layer."""


class ClusterJoinRejectedError(VeritasClusterError):
    """Raised when a peer rejects a join attempt — wrong cluster secret,
    stale/replayed proof, or a malformed request. Deliberately generic in
    its public message (see join_protocol.py) so a failed join never
    reveals *why* it failed to a potential attacker on the network."""


class ClusterConnectionError(VeritasClusterError):
    """Raised when a discovered peer's HTTP API cannot be reached at all."""
