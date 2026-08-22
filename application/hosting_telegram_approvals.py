"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Telegram presentation layer for a hosting purchase approval.  This module never
creates a provider resource: it only turns a one-time authorization into an
approved or cancelled authorization after Telegram's existing dual confirmation.
"""
from __future__ import annotations

from application.telegram_service import TelegramService
from infrastructure.hosting_governance import HostingOffer, HostingPurchaseGate, PurchaseAuthorization


class HostingTelegramApprovalWorkflow:
    def __init__(self, telegram: TelegramService, gate: HostingPurchaseGate) -> None:
        self._telegram = telegram
        self._gate = gate
        self._resolved: dict[str, PurchaseAuthorization] = {}

    def request(self, chat_id: str, offer: HostingOffer, *, ttl_seconds: float = 300.0) -> PurchaseAuthorization:
        authorization = self._gate.request(offer, ttl_seconds=ttl_seconds)
        description = (
            "تفويض استضافة لمرة واحدة فقط.\n"
            f"المزوّد: {offer.provider}\nالخطة: {offer.plan}\nالمنطقة: {offer.region}\n"
            f"المبلغ: {offer.monthly_price_minor} {offer.currency} / {offer.billing_period}\n"
            f"حدود البيانات: {offer.data_boundary}\nالموارد: {offer.compute_summary}\n"
            "الموافقة لا تنشئ مورداً ولا تدفع وحدها؛ يتطلب ذلك موصل مزود منفصلاً يستهلك هذا التفويض مرة واحدة."
        )
        self._telegram.request_approval(
            chat_id=chat_id,
            approval_id=authorization.authorization_id,
            description=description,
            on_approve=lambda: self._resolve_approved(authorization, offer),
            on_reject=lambda: self._resolve_cancelled(authorization),
        )
        return authorization

    def resolved(self, authorization_id: str) -> PurchaseAuthorization | None:
        return self._resolved.get(authorization_id)

    def _resolve_approved(self, authorization: PurchaseAuthorization, offer: HostingOffer) -> None:
        self._resolved[authorization.authorization_id] = self._gate.approve(authorization, offer)

    def _resolve_cancelled(self, authorization: PurchaseAuthorization) -> None:
        self._resolved[authorization.authorization_id] = self._gate.cancel(authorization)
