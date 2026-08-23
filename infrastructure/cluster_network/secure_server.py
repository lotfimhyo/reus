# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
SecureNodeServer: an HTTPS server requiring mutual TLS (each connecting
peer must present a certificate present in our trust bundle), exposing:

  GET  /health            -> liveness check
  GET  /peers             -> this node's known-peers list (Stage 4 discovery)
  POST /sync_knowledge     -> receive a signed KnowledgeItem from a peer
  POST /install_agent      -> receive a signed AgentSpec from a peer
  POST /raft/request_vote  -> Raft leader-election RPC
  POST /raft/append_entries -> Raft heartbeat / log-replication RPC
  POST /raft/install_snapshot -> Raft snapshot-catchup RPC (for a follower too far behind for normal replication)
  POST /submit_task        -> ask the (believed) leader to schedule a task
  POST /task_complete      -> a worker reporting a task finished

This is the Stage-2 stand-in for a gRPC service (see the module docstring
in `network/node.py` for why gRPC itself isn't used here).

For the Raft RPCs specifically, the sender's identity is taken from the
mTLS client certificate itself (`getpeercert()`), not merely from a claimed
field inside the JSON body — since heartbeats are frequent, we lean on the
transport-layer authentication already established by the TLS handshake
rather than re-signing every single heartbeat payload with Ed25519.
"""

import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _peer_common_name(ssl_socket) -> str | None:
    cert = ssl_socket.getpeercert()
    if not cert:
        return None
    for rdn in cert.get("subject", ()):
        for key, value in rdn:
            if key == "commonName":
                return value
    return None


class _BadRequestBody(Exception):
    """Raised by _read_body for any malformed/oversized request, so both
    _handle_signed_post and _handle_raw_post can respond with a clean 400
    instead of letting an uncaught ValueError (malformed Content-Length) or
    unbounded rfile.read() (no cap on size) reach the handler thread."""


# Generous enough for the largest expected payload (a Raft snapshot for a
# far-behind node), without an open ceiling that lets even an mTLS-trusted
# peer force an unbounded read.
_MAX_BODY_BYTES = 20 * 1024 * 1024  # 20MB


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - silence default access logs
        pass

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok", "node_id": self.server.node.node_id})
        elif self.path == "/peers":
            self._respond(200, self.server.node.handle_get_peers())
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        signed_route_names = {
            "/sync_knowledge": "handle_sync_knowledge",
            "/install_agent": "handle_install_agent",
        }
        raw_route_names = {
            "/raft/request_vote": "handle_request_vote",
            "/raft/append_entries": "handle_append_entries",
            "/raft/install_snapshot": "handle_install_snapshot",
            "/submit_task": "handle_submit_task",
            "/task_complete": "handle_task_complete",
            "/cluster/snapshot": "handle_cluster_snapshot",
        }

        # Resolved lazily (only the one attribute the requested path needs),
        # not eagerly for every route on every request: a `node` object is
        # free to implement only a subset of routes (e.g. ClusterSnapshotNode
        # implements just /peers and /cluster/snapshot) without those unused
        # routes' missing attributes ever being touched.
        if self.path in signed_route_names:
            handler = getattr(self.server.node, signed_route_names[self.path], None)
            if handler is None:
                self._respond(501, {"error": f"{self.path} not implemented by this node"})
                return
            self._handle_signed_post(handler)
        elif self.path in raw_route_names:
            handler = getattr(self.server.node, raw_route_names[self.path], None)
            if handler is None:
                self._respond(501, {"error": f"{self.path} not implemented by this node"})
                return
            self._handle_raw_post(handler)
        else:
            self._respond(404, {"error": "not found"})

    def _read_body(self) -> dict:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            raise _BadRequestBody(f"invalid Content-Length header: {raw_length!r}") from None
        if length < 0 or length > _MAX_BODY_BYTES:
            raise _BadRequestBody(f"Content-Length out of bounds: {length}")
        return json.loads(self.rfile.read(length))

    def _handle_signed_post(self, handler) -> None:
        try:
            body = self._read_body()
        except json.JSONDecodeError:
            self._respond(400, {"ok": False, "error": "invalid JSON"})
            return
        except _BadRequestBody as exc:
            self._respond(400, {"ok": False, "error": str(exc)})
            return
        ok, reason = handler(body)
        self._respond(200 if ok else 400, {"ok": ok, "reason": reason})

    def _handle_raw_post(self, handler) -> None:
        try:
            body = self._read_body()
        except json.JSONDecodeError:
            self._respond(400, {"error": "invalid JSON"})
            return
        except _BadRequestBody as exc:
            self._respond(400, {"error": str(exc)})
            return
        sender_cn = _peer_common_name(self.connection)
        result = handler(body, sender_cn)
        self._respond(200, result)

    def _respond(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class SecureNodeServer:
    def __init__(self, node, host: str, port: int, cert_path: str, key_path: str, trust_bundle_path: str):
        self.node = node
        self.host = host
        self.port = port

        self._httpd = ThreadingHTTPServer((host, port), _Handler)
        self._httpd.node = node  # type: ignore[attr-defined]

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
        ctx.load_verify_locations(cafile=trust_bundle_path)
        ctx.verify_mode = ssl.CERT_REQUIRED  # <-- this is what makes it *mutual* TLS
        self._ctx = ctx

        self._httpd.socket = ctx.wrap_socket(self._httpd.socket, server_side=True)
        self._thread: threading.Thread | None = None

    def refresh_trust(self, trust_bundle_path: str) -> None:
        """Add any newly-trusted peer certs (e.g. learned via discovery)
        to the already-running TLS context. `SSLContext.load_verify_locations`
        is additive, so previously trusted certs are unaffected; new
        connections immediately benefit, no restart needed."""
        self._ctx.load_verify_locations(cafile=trust_bundle_path)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
