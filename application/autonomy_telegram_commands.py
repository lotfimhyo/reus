"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Human-gated Telegram commands for autonomy proposals.  This adapter never
creates or promotes an agent itself: it only delegates a reviewed decision
to ``AutonomySupervisor`` after the generic Telegram confirmation gate.
"""
from __future__ import annotations

import uuid


class AutonomyTelegramCommands:
    def __init__(self, supervisor, ledger=None, telegram=None, governance=None) -> None:
        if ledger is None:
            ledger = governance
        if ledger is None or telegram is None:
            raise ValueError("AutonomyTelegramCommands requires governance ledger and Telegram service")
        self._supervisor = supervisor
        self._ledger = ledger
        self._telegram = telegram
        telegram.register_admin_command("/autonomy_pending", self._pending)
        telegram.register_admin_command("/autonomy_approve", self._approve)
        telegram.register_admin_command("/autonomy_reject", self._reject)

    def _send(self, chat_id: str, text: str) -> None:
        self._telegram.deliver(chat_id, text)

    def _proposal(self, proposal_id: str):
        if not proposal_id:
            return None
        try:
            return self._ledger.get(proposal_id)
        except (KeyError, ValueError):
            return None

    def _pending(self, chat_id: str, args: str) -> None:
        proposals = self._ledger.list_pending()
        if not proposals:
            self._send(chat_id, "لا توجد مقترحات استقلالية معلّقة.")
            return
        lines = [
            f"- {proposal.proposal_id} | القدرة: {proposal.draft.spec.capability} | "
            f"المخاطر: {proposal.draft.risk_level.value}"
            for proposal in proposals
        ]
        self._send(chat_id, "مقترحات الاستقلالية المعلّقة:\n" + "\n".join(lines))

    def _approve(self, chat_id: str, args: str) -> None:
        proposal_id = args.strip()
        proposal = self._proposal(proposal_id)
        if proposal is None:
            self._send(chat_id, "الاستخدام: /autonomy_approve <proposal_id> لمقترح معلّق.")
            return
        approval_id = f"autonomy-approve-{proposal_id}-{uuid.uuid4().hex[:8]}"
        self._telegram.request_approval(
            chat_id,
            approval_id,
            f"ترقية الوكيل المقترح للقدرة {proposal.draft.spec.capability} (المقترح {proposal_id}).",
            on_approve=lambda: self._execute_approve(chat_id, proposal_id),
            on_reject=lambda: self._send(chat_id, f"أُلغيت ترقية المقترح {proposal_id}."),
        )

    def _execute_approve(self, chat_id: str, proposal_id: str) -> None:
        if self._proposal(proposal_id) is None:
            self._send(chat_id, f"لم يعد المقترح {proposal_id} متاحاً للترقية.")
            return
        self._supervisor.approve(proposal_id, reviewer_note="approved through Telegram")
        self._send(chat_id, f"تم اعتماد المقترح {proposal_id} عبر الحوكمة.")

    def _reject(self, chat_id: str, args: str) -> None:
        proposal_id, _, note = args.strip().partition(" ")
        if not note.strip() or self._proposal(proposal_id) is None:
            self._send(chat_id, "الاستخدام: /autonomy_reject <proposal_id> <سبب الرفض>")
            return
        self._supervisor.reject(proposal_id, reviewer_note=note.strip())
        self._send(chat_id, f"تم رفض المقترح {proposal_id} مع تسجيل السبب.")
