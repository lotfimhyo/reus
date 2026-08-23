"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Cluster layer. What remains here after cleanup is live code: components used
by `infrastructure/node_runtime.py`, the production node composition, or by
its dependencies.

Historical context: this package previously contained an older join mechanism
based on an HMAC cluster secret and UDP discovery from the early project. That
mechanism was replaced by mTLS plus human Telegram approval through
`MTLSJoinClient` and `SecureRemoteExecutor`. mTLS is now the sole trust
mechanism. Before removing the obsolete code, repository-wide searches,
including tests, confirmed that the removed files were only referenced by one
another and had no live execution path.

Intentional import boundary: `MTLSJoinClient` and `SecureRemoteExecutor` are
not re-exported here even though they are the live implementations. Import them
directly from their modules, as node_runtime.py does. Re-exporting them here
creates a circular import with `infrastructure.cluster_network.cluster_snapshot_node`,
which imports peer_directory from this package during its own initialization.
Keeping direct module imports avoids that cycle.
"""

from infrastructure.cognitive_core.cluster.exceptions import (
    ClusterConnectionError,
    ClusterJoinRejectedError,
    VeritasClusterError,
)
from infrastructure.cognitive_core.cluster.peer_directory import PeerDirectory

__all__ = [
    "PeerDirectory",
    "VeritasClusterError",
    "ClusterConnectionError",
    "ClusterJoinRejectedError",
]
