"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

CapabilityEvolutionService supports reviewed capability evolution for nodes.

The complete flow has independently enforceable stages:
  1. A skill gap is described as an `AgentSpec` with at least one test case.
  2. `OllamaSynthesizer` writes the candidate implementation locally.
  3. `IndependentTestReviewer` performs a separate local-model review and
     proposes additional test cases; the code author does not review itself.
  4. `AgentCapabilityBinder.build()` applies static restrictions (no imports,
     `eval`, or dunder access) and then runs all test cases in an isolated,
     resource-limited subprocess sandbox.
  5. A successful candidate is placed in `PendingCapabilityStore` and
     administrators are notified in Telegram.
  6. Nothing is bound to `CapabilityLayer`, `LocalExecutor`, or a `NodeRole`
     until `/approve_capability` is followed by the separate `/approve`
     confirmation in the same double-confirmation gate used for other
     security-sensitive decisions.

Passing automated checks is necessary but not sufficient. Human approval is a
separate, non-bypassable requirement before a candidate capability is bound.
"""
from __future__ import annotations

import uuid
from typing import Optional

from application.telegram_service import TelegramService
from infrastructure.agent_factory.builder import BuildResult
from infrastructure.agent_factory.manifest import AgentSpec
from infrastructure.capability_binder import AgentCapabilityBinder
from infrastructure.cognitive_core.capability.descriptor import CapabilityDescriptor
from infrastructure.event_bus import Event, EventBus
from infrastructure.node_roles import NODE_ROLES
from infrastructure.pending_capabilities import PendingCapabilityRequest, PendingCapabilityStore


class CapabilityEvolutionService:
    def __init__(
        self,
        binder: AgentCapabilityBinder,
        pending_store: PendingCapabilityStore,
        telegram: TelegramService,
        admin_chat_ids: frozenset[str],
        event_bus: Optional[EventBus] = None,
    ):
        self._binder = binder
        self._pending = pending_store
        self._telegram = telegram
        self._admin_chat_ids = admin_chat_ids
        self._bus = event_bus

        telegram.register_admin_command("/pending_capabilities", self._cmd_pending)
        telegram.register_admin_command("/approve_capability", self._cmd_approve)
        telegram.register_admin_command("/reject_capability", self._cmd_reject)

    # -- Stages 1-5: proposal, build, and notification -----------------------

    def propose_capability(self, node_role_id: str, spec: AgentSpec) -> BuildResult:
        """Build through automated gates only; never bind or assume a later
        human decision. Always return `BuildResult` so callers can surface an
        automated rejection reason without an exception."""
        if node_role_id not in NODE_ROLES:
            raise ValueError(f"Unknown node role: {node_role_id!r}")

        result = self._binder.build(spec)
        if not result.approved:
            self._publish(
                "capability.evolution.rejected_automatically",
                {"node_role_id": node_role_id, "reason": result.reason},
            )
            return result

        request = self._pending.create(node_role_id, result)
        self._publish(
            "capability.evolution.pending_review",
            {"request_id": request.request_id, "node_role_id": node_role_id, "capability": spec.capability},
        )
        self._notify_admins(request)
        return result

    def _notify_admins(self, request: PendingCapabilityRequest) -> None:
        spec = request.build_result.spec
        text = (
            f"🧬 Ollama proposed a new capability for node '{request.node_role_id}':\n"
            f"Request ID: {request.request_id}\nCapability: {spec.capability}\nDescription: {spec.description}\n\n"
            f"It passed the complete automated pipeline (generation → static review → sandbox). "
            f"Review with: /approve_capability {request.request_id} or /reject_capability {request.request_id}"
        )
        for chat_id in self._admin_chat_ids:
            self._telegram.deliver(chat_id, text)

    # -- Telegram commands (stage 6: human oversight) ------------------------

    def _cmd_pending(self, chat_id: str, args: str) -> None:
        pending = self._pending.list_pending()
        if not pending:
            self._telegram.deliver(chat_id, "No proposed capabilities are pending.")
            return
        lines = [
            f"- {r.request_id} | node={r.node_role_id} | {r.build_result.spec.capability}" for r in pending
        ]
        self._telegram.deliver(chat_id, "Pending proposed capabilities:\n" + "\n".join(lines))

    def _cmd_approve(self, chat_id: str, args: str) -> None:
        request_id = args.strip()
        request = self._pending.get(request_id)
        if request is None or request.status != "pending":
            self._telegram.deliver(chat_id, f"No pending request exists with ID '{request_id}'.")
            return

        spec = request.build_result.spec
        approval_id = f"cap-approve-{uuid.uuid4().hex[:8]}"
        self._telegram.request_approval(
            chat_id,
            approval_id,
            f"Bind capability '{spec.capability}' to node '{request.node_role_id}' "
            f"(request ID: {request_id}). It will become executable immediately after approval.",
            on_approve=lambda: self._execute_approve(chat_id, request_id),
            on_reject=lambda: self._telegram.deliver(chat_id, f"Review of '{request_id}' was cancelled."),
        )

    def _execute_approve(self, chat_id: str, request_id: str) -> None:
        request = self._pending.get(request_id)
        if request is None or request.status != "pending":
            self._telegram.deliver(chat_id, f"Request '{request_id}' was no longer available for execution.")
            return

        descriptor: CapabilityDescriptor = self._binder.bind(request.build_result)
        role = NODE_ROLES[request.node_role_id]
        # NodeRole is a frozen dataclass with an intentionally mutable `specs`
        # list. Appending the approved capability grows the node's skill set at
        # runtime without redefining the source-level NODE_ROLES mapping.
        role.specs.append(request.build_result.spec)

        self._pending.mark_approved(request_id)
        self._publish(
            "capability.evolution.approved",
            {
                "request_id": request_id,
                "node_role_id": request.node_role_id,
                "capability_id": descriptor.capability_id,
            },
        )
        self._telegram.deliver(
            chat_id,
            f"✅ Capability '{descriptor.name}' was bound to node '{request.node_role_id}' "
            f"(capability_id={descriptor.capability_id}).",
        )

    def _cmd_reject(self, chat_id: str, args: str) -> None:
        request_id = args.strip()
        request = self._pending.mark_rejected(request_id)
        if request is None:
            self._telegram.deliver(chat_id, f"No request exists with ID '{request_id}'.")
            return
        self._publish("capability.evolution.rejected_by_human", {"request_id": request_id})
        self._telegram.deliver(
            chat_id, f"❌ Proposed capability '{request.build_result.spec.capability}' was rejected."
        )

    def _publish(self, name: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(Event(name=name, payload=payload))
