"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

First tests for DiscoveryService._gossip_round
(infrastructure/cluster_network/discovery.py), which previously had 0%
coverage. They mock the node, TrustStore, and client with no real network
sockets because the logic under test is the gossip policy itself—who is added,
who is ignored, and when state is saved—not the transport layer.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from infrastructure.cluster_network.discovery import DiscoveryService


class TestGossipRound(unittest.TestCase):
    def _make_node(self, known_peers=None):
        node = MagicMock()
        node.node_id = "self-node"
        node.trust_store.all_peers.return_value = known_peers or {}
        return node

    def test_does_nothing_when_client_not_yet_initialized(self):
        node = self._make_node()
        node._client = None
        service = DiscoveryService(node)

        service._gossip_round()

        node.trust_store.add_peer.assert_not_called()

    def test_skips_a_peer_whose_request_fails_and_continues(self):
        node = self._make_node(known_peers={"peer-a": {"host": "10.0.0.1", "port": 9000}})
        node._client.get_peers.side_effect = ConnectionError("unreachable")
        service = DiscoveryService(node)

        service._gossip_round()  # Must not leak an exception.

        node.trust_store.add_peer.assert_not_called()

    def test_ignores_a_falsy_response(self):
        node = self._make_node(known_peers={"peer-a": {"host": "10.0.0.1", "port": 9000}})
        node._client.get_peers.return_value = None
        service = DiscoveryService(node)

        service._gossip_round()

        node.trust_store.add_peer.assert_not_called()

    def test_learns_a_genuinely_new_peer_and_saves(self):
        node = self._make_node(known_peers={"peer-a": {"host": "10.0.0.1", "port": 9000}})
        node._client.get_peers.return_value = {
            "peers": {
                "peer-b": {
                    "host": "10.0.0.2",
                    "port": 9001,
                    "cert_pem": "FAKE_CERT",
                    "signing_pubkey_hex": "abcd",
                }
            }
        }
        service = DiscoveryService(node, allow_transitive_trust=True)

        service._gossip_round()

        node.trust_store.add_peer.assert_called_once_with(
            "peer-b", "10.0.0.2", 9001, "FAKE_CERT", "abcd"
        )
        node.trust_store.save.assert_called_once()
        node._rebuild_trust_bundle.assert_called_once()

    def test_discovery_does_not_grant_transitive_trust_by_default(self):
        node = self._make_node(known_peers={"peer-a": {"host": "10.0.0.1", "port": 9000}})
        node._client.get_peers.return_value = {
            "peers": {
                "peer-b": {
                    "host": "10.0.0.2",
                    "port": 9001,
                    "cert_pem": "CERT",
                    "signing_pubkey_hex": "abcd",
                }
            }
        }

        DiscoveryService(node)._gossip_round()

        node.trust_store.add_peer.assert_not_called()
        node.trust_store.save.assert_not_called()

    def test_does_not_re_add_an_already_known_peer(self):
        node = self._make_node(known_peers={"peer-a": {"host": "10.0.0.1", "port": 9000}})
        node._client.get_peers.return_value = {
            "peers": {"peer-a": {"host": "10.0.0.1", "port": 9000, "cert_pem": "X", "signing_pubkey_hex": "Y"}}
        }
        service = DiscoveryService(node)

        service._gossip_round()

        node.trust_store.add_peer.assert_not_called()
        node.trust_store.save.assert_not_called()
        node._rebuild_trust_bundle.assert_not_called()

    def test_does_not_learn_itself(self):
        node = self._make_node(known_peers={"peer-a": {"host": "10.0.0.1", "port": 9000}})
        node._client.get_peers.return_value = {
            "peers": {"self-node": {"host": "10.0.0.9", "port": 9999, "cert_pem": "X", "signing_pubkey_hex": "Y"}}
        }
        service = DiscoveryService(node)

        service._gossip_round()

        node.trust_store.add_peer.assert_not_called()

    def test_skips_save_and_rebuild_when_nothing_new_learned(self):
        """Existing performance optimization: avoid writing and rebuilding the
        trust bundle when no genuinely new node was added."""
        node = self._make_node(known_peers={"peer-a": {"host": "10.0.0.1", "port": 9000}})
        node._client.get_peers.return_value = {"peers": {}}
        service = DiscoveryService(node)

        service._gossip_round()

        node.trust_store.save.assert_not_called()
        node._rebuild_trust_bundle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
