"""Project: Reus | Developer: lotfi Mahiddine | Organization: Reulink."""
from infrastructure.cluster_network.join_requests import PendingJoinStore


def test_pending_join_survives_store_recreation(tmp_path):
    path = tmp_path / "pending_joins.json"
    store = PendingJoinStore(persist_path=str(path))
    created = store.create("node-1", "10.0.0.5", 8443, "CERT", "sign", "component", "now")

    recovered = PendingJoinStore(persist_path=str(path))
    assert recovered.get(created.request_id) is not None
    assert recovered.get(created.request_id).status == "pending"


def test_approved_join_is_removed_from_persisted_pending_set(tmp_path):
    path = tmp_path / "pending_joins.json"
    store = PendingJoinStore(persist_path=str(path))
    created = store.create("node-1", "10.0.0.5", 8443, "CERT", "sign", "component", "now")
    store.mark_approved(created.request_id)

    assert PendingJoinStore(persist_path=str(path)).list_pending() == []


def test_join_decisions_and_expiry_are_audited_persistently(tmp_path):
    path = tmp_path / "joins.json"
    audit_path = tmp_path / "joins.audit.jsonl"
    store = PendingJoinStore(str(path), max_age_seconds=60.0, audit_path=str(audit_path))
    request = store.create("node-a", "127.0.0.1", 8443, "cert", "sign", "component", "now")
    store.mark_rejected(request.request_id)
    expiring = store.create("node-b", "127.0.0.1", 8444, "cert", "sign", "component", "now")

    expiring.created_at = 0.0
    assert store.get(expiring.request_id).status == "expired"
    audit = audit_path.read_text(encoding="utf-8")
    assert '"event": "requested"' in audit
    assert '"event": "rejected"' in audit
    assert '"event": "expired"' in audit
