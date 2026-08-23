# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""Telegram application service.

It binds a Telegram chat to one agent through that agent's real token,
translates inbound messages into real workflows, and delivers task completion
or final failure through existing event subscriptions.

`/link` remains available to anyone with a valid agent token. In contrast,
sensitive administrative commands such as cloud deployment or model evolution
require an explicit `admin_chat_ids` allowlist and the general approval gate.
Non-allowlisted chats are audited and denied before reaching administrative
commands, whether or not they are linked to an agent.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from application.agent_token_service import AgentTokenService
from application.orchestrator_service import CreateWorkflowCommand, OrchestratorService
from domain.telegram_link import TelegramLink
from domain.telegram_link_repository import TelegramLinkRepository
from domain.workflow import TaskSpec
from infrastructure.event_bus import Event, EventBus
from infrastructure.approval_store import ApprovalRecord


class InvalidLinkToken(Exception):
    def __init__(self):
        super().__init__("Agent token is invalid or revoked.")


@dataclass
class PendingApproval:
    """General yes/no gate on which any future sensitive operation can rely."""

    approval_id: str
    description: str
    requested_by_chat_id: str
    on_approve: Callable[[], None]
    on_reject: Callable[[], None]
    created_at: float = field(default_factory=time.monotonic)
    expires_at: float = 0.0


class TelegramService:
    def __init__(
        self,
        link_repo: TelegramLinkRepository,
        token_service: AgentTokenService,
        orchestrator: OrchestratorService,
        event_bus: EventBus,
        admin_chat_ids: frozenset[str] = frozenset(),
        approval_ttl_seconds: float = 300.0,
        approval_store=None,
    ) -> None:
        self._links = link_repo
        self._tokens = token_service
        self._orchestrator = orchestrator
        self._bus = event_bus
        self._pending: dict[str, str] = {}  # task_id -> chat_id for delivering the result to its originating chat
        self._lock = threading.RLock()
        self._on_deliver: Callable[[str, str], None] | None = None

        self._admin_chat_ids = admin_chat_ids
        self._pending_approvals: dict[str, PendingApproval] = {}
        if approval_ttl_seconds <= 0:
            raise ValueError("approval_ttl_seconds must be greater than zero")
        self._approval_ttl_seconds = approval_ttl_seconds
        self._approval_store = approval_store
        if self._approval_store is not None:
            # A stored callback cannot be safely reconstructed.  Explicit
            # cancellation is safer than re-executing a stale deployment or
            # trust grant after restart; the record remains auditable.
            self._approval_store.cancel_unrecoverable_after_restart()
        # Additional administrative commands are registered here and never run
        # for a chat outside admin_chat_ids.
        self._admin_commands: dict[str, Callable[[str, str], None]] = {
            "/approve": lambda chat_id, args: self._handle_approval_response(chat_id, args, approved=True),
            "/reject": lambda chat_id, args: self._handle_approval_response(chat_id, args, approved=False),
        }

    def set_delivery_callback(self, callback: Callable[[str, str], None]) -> None:
        """Set the real delivery callback, normally `TelegramClient.send_message`.
        It is intentionally separate from construction to keep the service fully
        testable without a real Telegram client."""
        self._on_deliver = callback

    def start(self) -> None:
        """Subscribe to task completion and failure events once at startup."""
        self._bus.subscribe("task.completed", self._on_task_completed)
        self._bus.subscribe("task.failed", self._on_task_failed)

    def link(self, chat_id: str, token_plaintext: str) -> TelegramLink:
        token = self._tokens.authenticate(token_plaintext)
        if token is None:
            raise InvalidLinkToken()
        link = TelegramLink(chat_id=chat_id, agent_id=token.agent_id)
        self._links.add(link)
        return link

    def unlink(self, chat_id: str) -> None:
        self._links.delete(chat_id)

    # -- Administrative gate: sensitive commands and approvals ------------------

    def is_admin_chat(self, chat_id: str) -> bool:
        return chat_id in self._admin_chat_ids

    def register_admin_command(self, name: str, handler: Callable[[str, str], None]) -> None:
        """Register a handler invoked only for a chat in `admin_chat_ids`.
        This attaches later commands such as `/configure_cloud` or `/deploy_node`
        without changing this service."""
        self._admin_commands[name] = handler

    def request_approval(
        self,
        chat_id: str,
        approval_id: str,
        description: str,
        on_approve: Callable[[], None],
        on_reject: Callable[[], None],
    ) -> None:
        if not self.is_admin_chat(chat_id):
            raise PermissionError("sensitive approval may be requested only for an allowed admin chat")
        if not approval_id.strip():
            raise ValueError("approval_id must not be empty")
        with self._lock:
            if approval_id in self._pending_approvals:
                raise ValueError(f"approval {approval_id!r} already exists")
            now = time.time()
            self._pending_approvals[approval_id] = PendingApproval(
                approval_id=approval_id,
                description=description,
                requested_by_chat_id=chat_id,
                on_approve=on_approve,
                on_reject=on_reject,
                created_at=now,
                expires_at=now + self._approval_ttl_seconds,
            )
            if self._approval_store is not None:
                self._approval_store.expire_due(now)
                self._approval_store.create(
                    ApprovalRecord(
                        approval_id=approval_id,
                        description=description,
                        requested_by_chat_id=chat_id,
                        created_at=now,
                        expires_at=now + self._approval_ttl_seconds,
                    )
                )
        self._deliver(
            chat_id,
            f"⚠️ Approval required [{approval_id}]:\n{description}\n\n"
            f"Respond from this same administrative chat within {int(self._approval_ttl_seconds)} seconds: "
            f"/approve {approval_id} or /reject {approval_id}",
        )

    def _handle_approval_response(self, chat_id: str, args: str, approved: bool) -> None:
        approval_id = args.strip()
        if not approval_id:
            self._deliver(chat_id, "Usage: /approve <id> or /reject <id>")
            return
        if self._approval_store is not None:
            self._approval_store.expire_due()
        with self._lock:
            pending = self._pending_approvals.get(approval_id)
            if pending is not None and pending.expires_at <= time.time():
                self._pending_approvals.pop(approval_id, None)
                if self._approval_store is not None:
                    self._approval_store.transition(approval_id, "expired", "approval TTL elapsed")
                pending = None
                expired = True
            else:
                expired = False
            if pending is not None and pending.requested_by_chat_id != chat_id:
                self._deliver(chat_id, "A request created by another administrative chat cannot be confirmed here.")
                return
            if pending is not None:
                self._pending_approvals.pop(approval_id, None)
        if not pending:
            stored = self._approval_store.get(approval_id) if self._approval_store is not None else None
            if expired or (stored is not None and stored.status == "expired"):
                self._deliver(chat_id, f"Approval '{approval_id}' expired and no action was executed.")
            elif stored is not None and stored.status == "cancelled_restart":
                self._deliver(chat_id, f"Request '{approval_id}' was safely cancelled after restart; create a new request if it remains necessary.")
            else:
                self._deliver(chat_id, f"No pending approval exists with ID '{approval_id}'.")
            return
        try:
            if self._approval_store is not None:
                if approved:
                    if self._approval_store.transition(approval_id, "executing", "approval confirmed") is None:
                        self._deliver(chat_id, f"Decision '{approval_id}' cannot execute because its state changed.")
                        return
                else:
                    self._approval_store.transition(approval_id, "rejected", "rejected by administrator")
            (pending.on_approve if approved else pending.on_reject)()
        except Exception as exc:
            if self._approval_store is not None:
                self._approval_store.transition(
                    approval_id,
                    "failed",
                    f"execution failed: {type(exc).__name__}",
                    allowed_from=("executing",),
                )
            self._bus.publish(Event(name="admin.approval_execution_failed", payload={"approval_id": approval_id}))
            self._deliver(chat_id, f"Decision '{approval_id}' failed safely: {exc}")
            return
        if self._approval_store is not None and approved:
            self._approval_store.transition(
                approval_id,
                "approved",
                "execution completed",
                allowed_from=("executing",),
            )
        self._deliver(chat_id, f"{'Approved' if approved else 'Rejected'}: {approval_id}")

    def handle_incoming_message(self, chat_id: str, text: str) -> str:
        """Handle an inbound message and return its immediate acknowledgement.
        Final task success or failure arrives asynchronously through event
        callbacks, not through this method."""
        stripped = text.strip()
        first_word = stripped.split(maxsplit=1)[0] if stripped else ""

        if first_word in self._admin_commands:
            if not self.is_admin_chat(chat_id):
                self._bus.publish(Event(name="admin.command_denied", payload={"chat_id": chat_id, "command": first_word}))
                return "This command is restricted to authorized administrative chats."
            args = stripped[len(first_word):].strip()
            self._admin_commands[first_word](chat_id, args)
            return "✅"

        if stripped.startswith("/link"):
            parts = stripped.split(maxsplit=1)
            if len(parts) != 2:
                return "Usage: /link <agent token>"
            try:
                link = self.link(chat_id, parts[1].strip())
            except InvalidLinkToken:
                return (
                    "Token is invalid or revoked. To obtain a valid token, open the control "
                    "dashboard (/dashboard), open Agents, and generate a Telegram token next to "
                    "the agent you want to link. Paste the complete token after /link."
                )
            return f"Successfully linked to agent {link.agent_id}. Send any message to execute it as a task."

        if stripped == "/unlink":
            self.unlink(chat_id)
            return "This chat has been unlinked."

        link = self._links.get_by_chat_id(chat_id)
        if link is None:
            return "This chat is not linked yet. Use: /link <agent token>"

        workflow = self._orchestrator.create_workflow(
            CreateWorkflowCommand(
                name=f"telegram:{chat_id}",
                tasks=[TaskSpec(name="telegram-message", agent_id=link.agent_id, payload={"prompt": stripped})],
            )
        )
        task_id = next(iter(workflow.tasks.keys()))
        with self._lock:
            self._pending[task_id] = chat_id

        return "🛰️ Your task was received and is being processed."

    def _on_task_completed(self, event: Event) -> None:
        chat_id = self._pop_pending(event.payload.get("task_id"))
        if chat_id is None:
            return
        workflow = self._orchestrator.get_workflow(event.payload["workflow_id"])
        task = workflow.get_task(event.payload["task_id"])
        response = task.result.get("response") if isinstance(task.result, dict) else task.result
        self._deliver(chat_id, f"✅ Task completed:\n{response}")

    def _on_task_failed(self, event: Event) -> None:
        chat_id = self._pop_pending(event.payload.get("task_id"))
        if chat_id is None:
            return
        error = event.payload.get("error", "Unknown error")
        self._deliver(chat_id, f"❌ Task failed: {error}")

    def _pop_pending(self, task_id: str | None) -> str | None:
        if task_id is None:
            return None
        with self._lock:
            return self._pending.pop(task_id, None)

    def deliver(self, chat_id: str, text: str) -> None:
        """Public delivery point for external administrative commands so they do
        not access the internal `_deliver` method directly."""
        self._deliver(chat_id, text)

    def _deliver(self, chat_id: str, text: str) -> None:
        if self._on_deliver is not None:
            self._on_deliver(chat_id, text)
