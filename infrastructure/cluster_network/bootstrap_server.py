"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

BootstrapServer — deliberately PLAIN HTTP, not mTLS. This is the one
intentional exception in the whole cluster-network layer: a brand-new node
has no certificate any existing node trusts yet, so the very first contact
cannot itself be authenticated at the transport level (that would be
circular). Nothing sensitive is exchanged here, and nothing is trusted as a
side effect of this exchange alone — this server only ever does two things:

  POST /cluster/bootstrap-request
      Records the candidate's certificate + identity as PENDING. Returns a
      request_id. Does NOT add anything to TrustStore.
  GET  /cluster/bootstrap-status/<request_id>
      Reports pending/approved/rejected. Only on "approved" (which can only
      happen via a human /approve_peer in Telegram — see
      application/cluster_telegram_commands.py) does the response include
      this node's own certificate + address, so the requester can add THIS
      node as trusted too (mutual trust) and proceed over real mTLS for
      everything else (snapshot exchange, capability dispatch, Raft).

Trust itself is granted exactly once, exactly by TrustStore.add_peer(),
exactly from the Telegram approval handler — never from this server.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from infrastructure.cluster_network.join_requests import PendingJoinStore


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - silence default access logs
        pass

    def _respond(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/cluster/bootstrap-request":
            self._respond(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            required = (
                "node_id",
                "host",
                "mtls_port",
                "cert_pem",
                "signing_pubkey_hex",
                "component_public_key_hex",
                "component_created_at",
            )
            missing = [k for k in required if k not in body]
            if missing:
                self._respond(400, {"error": f"missing fields: {missing}"})
                return
        except (json.JSONDecodeError, TypeError, ValueError):
            self._respond(400, {"error": "invalid JSON"})
            return

        server = self.server
        request = server.pending_store.create(
            node_id=body["node_id"],
            host=body["host"],
            mtls_port=int(body["mtls_port"]),
            cert_pem=body["cert_pem"],
            signing_pubkey_hex=body["signing_pubkey_hex"],
            component_public_key_hex=body["component_public_key_hex"],
            component_created_at=body["component_created_at"],
        )
        server.on_request_received(request)
        self._respond(202, {"request_id": request.request_id, "status": "pending"})

    def do_GET(self):
        prefix = "/cluster/bootstrap-status/"
        if not self.path.startswith(prefix):
            self._respond(404, {"error": "not found"})
            return
        request_id = self.path[len(prefix):]
        server = self.server
        request = server.pending_store.get(request_id)
        if request is None:
            self._respond(404, {"error": "unknown request_id"})
            return

        payload = {"status": request.status}
        if request.status == "approved":
            payload["responder"] = server.own_identity_payload()
        self._respond(200, payload)


class BootstrapServer:
    def __init__(
        self,
        pending_store: PendingJoinStore,
        own_identity_payload_fn,
        host: str,
        port: int,
        on_request_received=None,
    ):
        """`own_identity_payload_fn()` returns this node's own
        {node_id, host, mtls_port, cert_pem, signing_pubkey_hex,
        component_public_key_hex, component_created_at} dict — supplied as
        a callable (not a plain dict) since a node's own address/cert can
        legitimately change across the server's lifetime.
        `on_request_received(request)` is an optional hook (used to notify
        Telegram admins that a new peer wants to join) — kept separate from
        the HTTP handler so it can be swapped/muted in tests."""
        self.pending_store = pending_store
        self.own_identity_payload = own_identity_payload_fn
        self.on_request_received = on_request_received or (lambda request: None)
        self.host = host
        self.port = port

        self._httpd = ThreadingHTTPServer((host, port), _Handler)
        self._httpd.pending_store = pending_store
        self._httpd.own_identity_payload = own_identity_payload_fn
        self._httpd.on_request_received = self.on_request_received
        self._thread = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
