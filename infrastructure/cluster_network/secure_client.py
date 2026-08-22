# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
SecureNodeClient: sends requests to a peer node over mutual TLS.
"""

import http.client
import json
import ssl
from typing import Optional


class SecureNodeClient:
    def __init__(self, own_cert_path: str, own_key_path: str, trust_bundle_path: str):
        self._own_cert_path = own_cert_path
        self._own_key_path = own_key_path
        self._ctx = self._build_context(trust_bundle_path)

    def _build_context(self, trust_bundle_path: str) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(cafile=trust_bundle_path)
        ctx.load_cert_chain(certfile=self._own_cert_path, keyfile=self._own_key_path)
        # Self-signed certs use the node_id as CN, not a resolvable DNS
        # hostname, so hostname checking is disabled; trust instead comes
        # from the cert being present in the trust bundle at all.
        ctx.check_hostname = False
        return ctx

    def refresh_trust(self, trust_bundle_path: str) -> None:
        """See SecureNodeServer.refresh_trust — same additive reasoning
        applies to the client side's verification of servers it connects to."""
        self._ctx.load_verify_locations(cafile=trust_bundle_path)

    def post_json(self, host: str, port: int, path: str, obj: dict, timeout: float = 5.0) -> Optional[dict]:
        conn = http.client.HTTPSConnection(host, port, context=self._ctx, timeout=timeout)
        try:
            body = json.dumps(obj).encode("utf-8")
            conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            return json.loads(resp.read())
        finally:
            conn.close()

    def get_json(self, host: str, port: int, path: str, timeout: float = 5.0) -> Optional[dict]:
        conn = http.client.HTTPSConnection(host, port, context=self._ctx, timeout=timeout)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            return json.loads(resp.read())
        finally:
            conn.close()

    # -- convenience wrappers -------------------------------------------------

    def send_knowledge(self, host: str, port: int, signed_envelope: dict, timeout: float = 5.0) -> Optional[dict]:
        return self.post_json(host, port, "/sync_knowledge", signed_envelope, timeout)

    def send_agent_spec(self, host: str, port: int, signed_envelope: dict, timeout: float = 5.0) -> Optional[dict]:
        return self.post_json(host, port, "/install_agent", signed_envelope, timeout)

    def health_check(self, host: str, port: int, timeout: float = 5.0) -> Optional[dict]:
        return self.get_json(host, port, "/health", timeout)

    def get_peers(self, host: str, port: int, timeout: float = 5.0) -> Optional[dict]:
        return self.get_json(host, port, "/peers", timeout)

    def request_vote(self, host: str, port: int, payload: dict, timeout: float = 1.0) -> Optional[dict]:
        return self.post_json(host, port, "/raft/request_vote", payload, timeout)

    def append_entries(self, host: str, port: int, payload: dict, timeout: float = 1.0) -> Optional[dict]:
        return self.post_json(host, port, "/raft/append_entries", payload, timeout)

    def install_snapshot(self, host: str, port: int, payload: dict, timeout: float = 5.0) -> Optional[dict]:
        return self.post_json(host, port, "/raft/install_snapshot", payload, timeout)

    def submit_task(self, host: str, port: int, payload: dict, timeout: float = 5.0) -> Optional[dict]:
        return self.post_json(host, port, "/submit_task", payload, timeout)

    def report_task_complete(self, host: str, port: int, payload: dict, timeout: float = 5.0) -> Optional[dict]:
        return self.post_json(host, port, "/task_complete", payload, timeout)
