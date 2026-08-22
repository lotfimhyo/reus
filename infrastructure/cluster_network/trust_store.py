# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
TrustStore: the registry of known, trusted peer nodes.

Stage 2/3 used a manually-curated `peers.json`. Stage 4 adds automatic
discovery (`discovery.py`) on top of the same store, so peer records must
now be self-contained and *portable* — a node's certificate is stored as
its actual PEM content, not a local file path, since a gossiped peer
record has to make sense on a machine that never had that file on disk.

Being present in this store (and therefore in the mTLS trust bundle built
from it) is what makes a peer trusted at the transport level, since every
node's certificate is self-signed.
"""

import json
import os
from typing import Dict, Optional

from infrastructure.cluster_network.certs import certificate_common_name


class TrustStore:
    def __init__(self, peers_file: str):
        self._peers_file = peers_file
        self._peers: Dict[str, dict] = {}
        if os.path.exists(peers_file):
            with open(peers_file, "r", encoding="utf-8") as f:
                self._peers = json.load(f)

    def add_peer(self, node_id: str, host: str, port: int, cert_pem: str, signing_pubkey_hex: str) -> bool:
        """Returns True if this was a new peer (useful for discovery to
        know whether the trust bundle needs rebuilding)."""
        transport_node_id = certificate_common_name(cert_pem)
        existing = self._peers.get(node_id)
        if existing is not None and existing.get("cert_pem") != cert_pem:
            raise ValueError(
                f"refusing automatic certificate rotation for trusted node {node_id!r}; "
                "revoke and re-approve the node through the governance workflow"
            )
        if any(
            peer_id != node_id and peer.get("transport_node_id") == transport_node_id
            for peer_id, peer in self._peers.items()
        ):
            raise ValueError(f"transport identity {transport_node_id!r} is already bound to another peer")

        is_new = existing is None
        self._peers[node_id] = {
            "host": host,
            "port": port,
            "cert_pem": cert_pem,
            "signing_pubkey_hex": signing_pubkey_hex,
            "transport_node_id": transport_node_id,
        }
        return is_new

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._peers_file) or ".", exist_ok=True)
        with open(self._peers_file, "w", encoding="utf-8") as f:
            json.dump(self._peers, f, ensure_ascii=False, indent=2)

    def get_peer(self, node_id: str) -> Optional[dict]:
        return self._peers.get(node_id)

    def get_peer_by_transport_id(self, transport_node_id: str) -> Optional[dict]:
        for peer in self._peers.values():
            peer_transport_id = peer.get("transport_node_id")
            if peer_transport_id == transport_node_id:
                return dict(peer)
            # Backward compatibility for TrustStore files written before the
            # transport identifier was stored explicitly.
            if peer_transport_id is None and certificate_common_name(peer["cert_pem"]) == transport_node_id:
                return dict(peer)
        return None

    def transport_peer_ids(self) -> list[str]:
        return [
            peer.get("transport_node_id") or certificate_common_name(peer["cert_pem"])
            for peer in self._peers.values()
        ]

    def all_peers(self) -> Dict[str, dict]:
        return dict(self._peers)

    def build_trust_bundle(self, bundle_path: str, own_cert_pem: Optional[str] = None) -> str:
        """Concatenate all trusted peer certs (+ optionally our own) into a
        single PEM file, suitable as an SSL `cafile` for mTLS verification."""
        os.makedirs(os.path.dirname(bundle_path) or ".", exist_ok=True)
        with open(bundle_path, "w", encoding="utf-8") as out:
            for peer in self._peers.values():
                out.write(peer["cert_pem"])
                out.write("\n")
            if own_cert_pem:
                out.write(own_cert_pem)
                out.write("\n")
        return bundle_path
