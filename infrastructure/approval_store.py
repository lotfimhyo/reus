"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Durable audit metadata for sensitive Telegram approvals.  Execution callbacks
are intentionally never serialized; a restart cancels unresolved approvals
instead of attempting to replay an action whose current safety conditions can
no longer be proven.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ApprovalRecord:
    approval_id: str
    description: str
    requested_by_chat_id: str
    created_at: float
    expires_at: float
    status: str = "pending"
    final_reason: str = ""


class FileApprovalStore:
    """Atomically persists approval metadata plus append-only audit events."""

    def __init__(self, records_path: str, audit_path: str | None = None) -> None:
        self._path = Path(records_path)
        self._audit_path = Path(audit_path or f"{records_path}.audit.jsonl")
        self._lock = threading.RLock()
        self._records: dict[str, ApprovalRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        records = json.loads(self._path.read_text(encoding="utf-8"))
        self._records = {record["approval_id"]: ApprovalRecord(**record) for record in records}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temporary.write_text(json.dumps([asdict(record) for record in self._records.values()], sort_keys=True), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self._path)

    def _audit(self, event: str, record: ApprovalRecord) -> None:
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        event_line = {
            "event": event,
            "at": time.time(),
            "approval_id": record.approval_id,
            "requested_by_chat_id": record.requested_by_chat_id,
            "status": record.status,
            "reason": record.final_reason,
        }
        with self._audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event_line, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(self._audit_path, 0o600)

    def create(self, record: ApprovalRecord) -> None:
        with self._lock:
            if record.approval_id in self._records:
                raise ValueError(f"approval {record.approval_id!r} already exists")
            self._records[record.approval_id] = record
            self._save()
            self._audit("created", record)

    def get(self, approval_id: str) -> ApprovalRecord | None:
        with self._lock:
            record = self._records.get(approval_id)
            return None if record is None else ApprovalRecord(**asdict(record))

    def transition(
        self,
        approval_id: str,
        status: str,
        reason: str = "",
        allowed_from: tuple[str, ...] = ("pending",),
    ) -> ApprovalRecord | None:
        with self._lock:
            record = self._records.get(approval_id)
            if record is None or record.status not in allowed_from:
                return None
            record.status = status
            record.final_reason = reason
            self._save()
            self._audit(status, record)
            return ApprovalRecord(**asdict(record))

    def expire_due(self, now: float | None = None) -> list[ApprovalRecord]:
        current_time = time.time() if now is None else now
        with self._lock:
            expired = [record for record in self._records.values() if record.status == "pending" and record.expires_at <= current_time]
            for record in expired:
                record.status = "expired"
                record.final_reason = "approval TTL elapsed"
            if expired:
                self._save()
                for record in expired:
                    self._audit("expired", record)
            return [ApprovalRecord(**asdict(record)) for record in expired]

    def cancel_unrecoverable_after_restart(self) -> list[ApprovalRecord]:
        """Fail closed: callbacks are memory-only and are never replayed."""
        with self._lock:
            cancelled = [record for record in self._records.values() if record.status == "pending"]
            for record in cancelled:
                record.status = "cancelled_restart"
                record.final_reason = "process restarted; execution callback was deliberately not restored"
            if cancelled:
                self._save()
                for record in cancelled:
                    self._audit("cancelled_restart", record)
            return [ApprovalRecord(**asdict(record)) for record in cancelled]
