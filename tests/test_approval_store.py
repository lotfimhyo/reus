"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
from pathlib import Path

from application.telegram_service import TelegramService
from infrastructure.approval_store import FileApprovalStore
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.telegram_link_repository import InMemoryTelegramLinkRepository


class _Tokens:
    def authenticate(self, plaintext):
        return None


class _Orchestrator:
    pass


def _service(store: FileApprovalStore) -> TelegramService:
    return TelegramService(
        link_repo=InMemoryTelegramLinkRepository(),
        token_service=_Tokens(),
        orchestrator=_Orchestrator(),
        event_bus=InMemoryEventBus(),
        admin_chat_ids=frozenset({"admin"}),
        approval_store=store,
    )


def test_restart_cancels_unrecoverable_approval_and_keeps_audit_trail(tmp_path: Path):
    records_path = tmp_path / "approvals.json"
    audit_path = tmp_path / "approvals.audit.jsonl"
    first_store = FileApprovalStore(str(records_path), str(audit_path))
    first_service = _service(first_store)
    first_service.request_approval("admin", "deployment-1", "نشر حساس", lambda: None, lambda: None)
    assert first_store.get("deployment-1").status == "pending"

    second_store = FileApprovalStore(str(records_path), str(audit_path))
    second_service = _service(second_store)
    delivered, executed = [], []
    second_service.set_delivery_callback(lambda chat_id, text: delivered.append((chat_id, text)))
    second_service.handle_incoming_message("admin", "/approve deployment-1")

    assert executed == []
    assert second_store.get("deployment-1").status == "cancelled_restart"
    assert "أُلغي الطلب" in delivered[-1][1]
    audit_events = audit_path.read_text(encoding="utf-8")
    assert '"event": "created"' in audit_events
    assert '"event": "cancelled_restart"' in audit_events
