# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
DiscoveryService: automatic, gossip-style propagation of cluster
membership on top of the mTLS trust layer.

Honest scope: this does NOT solve "trust a stranger from nothing" — that
would be insecure by construction (anyone could then join and read/write
cluster state). What it solves is "after ONE manually-established trust
link to a seed node (Stage 2's `trust_peer`), automatically learn about
every OTHER node the seed (and its peers, transitively) already trusts,"
without an operator having to manually pair every node with every other
node. This mirrors how real cluster-membership protocols (e.g. Consul,
Serf/SWIM) still require an initial join token/seed address — discovery
propagates membership, it doesn't manufacture trust from nothing.

Mechanism: every `interval_seconds`, ask each currently-known peer for
its own `/peers` list over mTLS. A discovered peer is only an observation,
not a trust grant: automatic transitive trust is disabled by default because
a compromised trusted node must not be able to introduce arbitrary nodes.
Operators who intentionally use a managed trust domain can enable it
explicitly.
"""

import threading


class DiscoveryService:
    def __init__(self, node, interval_seconds: float = 1.0, allow_transitive_trust: bool = False):
        self._node = node
        self.interval_seconds = interval_seconds
        self.allow_transitive_trust = allow_transitive_trust
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._gossip_round()
            self._stop_event.wait(self.interval_seconds)

    def _gossip_round(self) -> None:
        node = self._node
        if node._client is None:
            return

        known_peers = node.trust_store.all_peers()
        for peer_id, peer in list(known_peers.items()):
            try:
                response = node._client.get_peers(peer["host"], peer["port"])
            except (ConnectionError, OSError, TimeoutError):
                continue
            if not response:
                continue

            if not self.allow_transitive_trust:
                continue

            learned_anything = False
            for candidate_id, candidate in response.get("peers", {}).items():
                if candidate_id == node.node_id or candidate_id in node.trust_store.all_peers():
                    continue
                node.trust_store.add_peer(
                    candidate_id,
                    candidate["host"],
                    candidate["port"],
                    candidate["cert_pem"],
                    candidate["signing_pubkey_hex"],
                )
                learned_anything = True

            if learned_anything:
                node.trust_store.save()
                node._rebuild_trust_bundle()
