"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

ClusterTelegramCommands — the human-oversight side of the mTLS trust
bootstrap: /pending_peers, /approve_peer, /reject_peer. All three are
admin commands (register_admin_command), so — exactly like
CloudTelegramCommands — any chat outside admin_chat_ids is silently
denied before this code even runs. /approve_peer additionally goes
through TelegramService.request_approval (the same double-confirmation
gate used for cloud instance deploy/destroy), because granting a new
device mTLS trust is exactly as security-sensitive as provisioning cloud
infrastructure — an admin chat being on the allowlist should not be
enough on its own for an irreversible trust decision to happen from a
single fat-fingered message.
"""
from __future__ import annotations

import uuid

from application.telegram_service import TelegramService
from infrastructure.cluster_network.join_requests import PendingJoinStore
from infrastructure.cluster_network.trust_store import TrustStore
from infrastructure.event_bus import Event, EventBus


class ClusterTelegramCommands:
    def __init__(
        self,
        service: TelegramService,
        pending_store: PendingJoinStore,
        trust_store: TrustStore,
        trust_bundle_path: str,
        admin_chat_ids: frozenset[str],
        event_bus: EventBus | None = None,
        on_peer_approved=None,
    ):
        """`admin_chat_ids` is passed explicitly (not read back off
        `service`) because notifying every admin chat of a new pending
        request (`on_request_received` from BootstrapServer) needs the
        same list. `on_peer_approved(request)` is an optional hook, e.g.
        to call `SecureNodeServer.refresh_trust` / `SecureNodeClient.
        refresh_trust` on an already-running server/client without a
        restart."""
        self._service = service
        self._pending = pending_store
        self._trust_store = trust_store
        self._trust_bundle_path = trust_bundle_path
        self._admin_chat_ids = admin_chat_ids
        self._bus = event_bus
        self._on_peer_approved = on_peer_approved or (lambda request: None)

        service.register_admin_command("/pending_peers", self._cmd_pending)
        service.register_admin_command("/approve_peer", self._cmd_approve_peer)
        service.register_admin_command("/reject_peer", self._cmd_reject_peer)

    def _publish(self, name: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(Event(name=name, payload=payload))

    def _send(self, chat_id: str, text: str) -> None:
        self._service.deliver(chat_id, text)

    def notify_new_request(self, request) -> None:
        """Wired as BootstrapServer's `on_request_received` hook — fans out
        to every admin chat, not just the one that happens to send the next
        command, since bootstrap requests arrive from the network, not from
        Telegram."""
        self._publish(
            "cluster.peer_join_requested",
            {"request_id": request.request_id, "node_id": request.node_id, "host": request.host},
        )
        for chat_id in self._admin_chat_ids:
            self._send(
                chat_id,
                f"🔔 New node join request:\n"
                f"Request ID: {request.request_id}\nnode_id: {request.node_id}\nHost: {request.host}\n\n"
                f"Review with: /approve_peer {request.request_id} or /reject_peer {request.request_id}",
            )

    def _cmd_pending(self, chat_id: str, args: str) -> None:
        pending = self._pending.list_pending()
        if not pending:
            self._send(chat_id, "No node join requests are pending.")
            return
        lines = [f"- {r.request_id} | node_id={r.node_id} | {r.host}" for r in pending]
        self._send(chat_id, "Pending node join requests:\n" + "\n".join(lines))

    def _cmd_approve_peer(self, chat_id: str, args: str) -> None:
        request_id = args.strip()
        request = self._pending.get(request_id)
        if request is None or request.status != "pending":
            self._send(chat_id, f"No pending request exists with ID '{request_id}'.")
            return

        approval_id = f"peer-approve-{uuid.uuid4().hex[:8]}"
        self._service.request_approval(
            chat_id,
            approval_id,
            f"Grant mTLS trust to node_id={request.node_id} at {request.host} "
            f"(request ID: {request_id}). This grant cannot be automatically reversed.",
            on_approve=lambda: self._execute_approve(chat_id, request_id),
            on_reject=lambda: self._send(chat_id, f"Review of '{request_id}' was cancelled."),
        )

    def _execute_approve(self, chat_id: str, request_id: str) -> None:
        request = self._pending.get(request_id)
        if request is None or request.status != "pending":
            self._send(chat_id, f"Request '{request_id}' was no longer available for execution.")
            return

        # Trust must be fully granted BEFORE the pending request is marked
        # approved: a concurrent poller (BootstrapClient.poll_until_decided)
        # reads status over the network and, on "approved", immediately
        # proceeds to connect over mTLS. Marking approved first would open a
        # real race window where the poller sees "approved" before
        # TrustStore.add_peer()/refresh_trust() have actually run.
        self._trust_store.add_peer(
            request.node_id, request.host, request.mtls_port, request.cert_pem, request.signing_pubkey_hex
        )
        self._trust_store.save()
        self._trust_store.build_trust_bundle(self._trust_bundle_path)
        self._on_peer_approved(request)

        self._pending.mark_approved(request_id)

        self._publish(
            "cluster.peer_approved",
            {"request_id": request_id, "node_id": request.node_id, "host": request.host},
        )
        self._send(chat_id, f"✅ Trust granted: node {request.node_id} is now in the TrustStore.")

    def _cmd_reject_peer(self, chat_id: str, args: str) -> None:
        request_id = args.strip()
        request = self._pending.mark_rejected(request_id)
        if request is None:
            self._send(chat_id, f"No request exists with ID '{request_id}'.")
            return
        self._publish(
            "cluster.peer_rejected", {"request_id": request_id, "node_id": request.node_id}
        )
        self._send(chat_id, f"❌ Node join request for {request.node_id} was rejected.")
