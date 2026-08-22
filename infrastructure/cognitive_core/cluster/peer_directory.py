"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

PeerDirectory — the piece Hybrid/Cloud Mode's design (section 6) needed but
section 3's join protocol alone didn't produce: knowing WHICH peer node to
ask for a given cached capability. IdentityRegistry (Layer 1) knows peers'
cryptographic identities; PeerDirectory separately tracks their reachable
REST API addresses and, for capabilities cached via a join snapshot, which
node actually owns/can execute them.

Design decision (kept out of Capability Registry itself): a
CapabilityDescriptor's `component_id` names the owning *agent*, not
necessarily which physical *node* that agent's handler runs on — and
Capability Registry (Layer 4) has no reason to know about cluster topology
at all. This mapping lives entirely in the cluster layer instead, so Layer
4 stays exactly as unaware of Hybrid Mode as every other pre-existing
layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_PEERS_FILENAME = "peers.json"


class PeerDirectory:
    """Local, file-persisted map of node_component_id -> API base URL, and
    capability_id -> owning node_component_id (for cached/imported
    capabilities only — locally-owned capabilities need no entry here)."""

    def __init__(self, data_dir: str | Path):
        self.path = Path(data_dir) / _PEERS_FILENAME
        self._node_addresses: dict[str, str] = {}
        self._capability_origins: dict[str, str] = {}
        self._load()

    def register_node(self, node_component_id: str, api_base_url: str) -> None:
        """Record (or refresh) a peer node's reachable address. Safe to
        call repeatedly — e.g. every time a presence announcement is
        heard, not only on first join — since an address can change
        (DHCP) after the initial join."""
        self._node_addresses[node_component_id] = api_base_url
        self._save()

    def node_address(self, node_component_id: str) -> Optional[str]:
        return self._node_addresses.get(node_component_id)

    def register_capability_origin(self, capability_id: str, node_component_id: str) -> None:
        self._capability_origins[capability_id] = node_component_id
        self._save()

    def capability_origin(self, capability_id: str) -> Optional[str]:
        return self._capability_origins.get(capability_id)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "node_addresses": self._node_addresses,
                    "capability_origins": self._capability_origins,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._node_addresses = data.get("node_addresses", {})
        self._capability_origins = data.get("capability_origins", {})
