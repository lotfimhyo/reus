"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class ControlPlanePairing:
    pairing_id: str
    panel_url: str
    core_url: str
    claim_hash: str
    created_at: float
    expires_at: float
    status: str = "pending"
    user_key_hash: str | None = None


class ControlPlanePairingStore:
    """Local durable state; claim and user key plaintext are never serialized."""

    def __init__(self, state_path: str, audit_path: str) -> None:
        self._state = Path(state_path); self._audit = Path(audit_path); self._state.parent.mkdir(parents=True, exist_ok=True); self._audit.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, ControlPlanePairing] = {}
        self._load()

    def create(self, pairing_id: str, panel_url: str, core_url: str, ttl_seconds: float) -> tuple[ControlPlanePairing, str]:
        self.expire_due(); claim = secrets.token_urlsafe(32); now = time.time()
        record = ControlPlanePairing(pairing_id, panel_url, core_url, _hash(claim), now, now + ttl_seconds)
        self._records[pairing_id] = record; self._persist(); self._audit_event("created", record)
        return record, claim

    def consume_claim_and_issue_key(self, pairing_id: str, claim: str) -> tuple[ControlPlanePairing, str]:
        self.expire_due(); record = self._records.get(pairing_id)
        if record is None or record.status != "pending" or not secrets.compare_digest(record.claim_hash, _hash(claim)):
            raise ValueError("unknown, expired, or already used control-plane claim")
        user_key = secrets.token_urlsafe(32); record.status = "active"; record.user_key_hash = _hash(user_key); self._persist(); self._audit_event("activated", record)
        return record, user_key

    def verify_user_key(self, supplied: str) -> bool:
        self.expire_due(); return any(record.status == "active" and record.user_key_hash and secrets.compare_digest(record.user_key_hash, _hash(supplied)) for record in self._records.values())

    def revoke(self, pairing_id: str) -> bool:
        record = self._records.get(pairing_id)
        if record is None or record.status != "active": return False
        record.status = "revoked"; record.user_key_hash = None; self._persist(); self._audit_event("revoked", record); return True

    def expire_due(self) -> None:
        now = time.time(); changed = False
        for record in self._records.values():
            if record.status == "pending" and record.expires_at <= now:
                record.status = "expired"; changed = True; self._audit_event("expired", record)
        if changed: self._persist()

    def _load(self) -> None:
        if not self._state.exists(): return
        try:
            for item in json.loads(self._state.read_text("utf-8")):
                record = ControlPlanePairing(**item); self._records[record.pairing_id] = record
        except (OSError, ValueError, TypeError):
            self._records = {}

    def _persist(self) -> None:
        data = json.dumps([asdict(record) for record in self._records.values()], ensure_ascii=False, sort_keys=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self._state.parent, delete=False) as tmp:
            tmp.write(data); temp = tmp.name
        os.chmod(temp, 0o600); os.replace(temp, self._state); os.chmod(self._state, 0o600)

    def _audit_event(self, event: str, record: ControlPlanePairing) -> None:
        payload = {"event": event, "pairing_id": record.pairing_id, "panel_url": record.panel_url, "core_url": record.core_url, "status": record.status, "at": time.time()}
        with self._audit.open("a", encoding="utf-8") as handle: handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        os.chmod(self._audit, 0o600)
