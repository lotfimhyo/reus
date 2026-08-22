# Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink
import json

import pytest

from infrastructure.control_plane_pairing_store import ControlPlanePairingStore


def test_claim_is_hashed_consumed_once_and_issues_scoped_user_key(tmp_path):
    state = tmp_path / "pairings.json"
    store = ControlPlanePairingStore(str(state), str(tmp_path / "pairings.audit.jsonl"))
    record, claim = store.create("panel-example", "https://panel.example", "https://core.example", 60)

    assert claim not in state.read_text("utf-8")
    assert record.claim_hash != claim
    activated, user_key = store.consume_claim_and_issue_key("panel-example", claim)
    assert activated.status == "active"
    assert len(user_key) >= 32
    assert store.verify_user_key(user_key)
    with pytest.raises(ValueError):
        store.consume_claim_and_issue_key("panel-example", claim)
    with pytest.raises(ValueError):
        store.consume_claim_and_issue_key("panel-example", "wrong-claim")
    audit = "\n".join(json.loads(line).__str__() for line in (tmp_path / "pairings.audit.jsonl").read_text("utf-8").splitlines())
    assert claim not in audit
    assert user_key not in audit
