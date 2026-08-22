"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

PendingJoinStore — resolves the open architectural decision left by the
previous increment ("Veritas cluster-secret join" vs "Phoenix mTLS trust
pairing"): mTLS/TrustStore is now the single trust mechanism for the whole
cluster (see bootstrap_server.py / bootstrap_client.py / cluster_telegram_
commands.py). The piece that was missing to make mTLS trust pairing work
WITHOUT a manual out-of-band certificate copy (the reason Veritas's simpler
mechanism existed in the first place) is this: a bounded, human-gated
"bootstrap" step. A new node presents its certificate over a plain,
unauthenticated channel; nothing is trusted yet; a human administrator
approves or rejects it via Telegram (the same admin_chat_ids allowlist and
request_approval gate already used for cloud deployment). Only on approval
does the node's certificate enter TrustStore and become part of the mTLS
trust bundle — mirroring Project Phoenix's explicit prior decision that
"a Telegram approval step" does not license anything the underlying
mechanism wouldn't otherwise allow: here, it is the ONLY thing that grants
trust; there is no fallback silent-trust path.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PendingJoinRequest:
    request_id: str
    node_id: str
    host: str
    mtls_port: int
    cert_pem: str
    signing_pubkey_hex: str
    component_public_key_hex: str
    component_created_at: str
    status: str = "pending"  # pending | approved | rejected | expired
    created_at: float = field(default_factory=time.time)


class PendingJoinStore:
    """طلبات انضمام مقيدة بزمن، اختيارية الحفظ على القرص.

    تخزن هذه الطبقة شهادات عامة وبيانات تعريف عقدة فقط، لا مفاتيح خاصة. وعند
    تفعيل persist_path تحفظ الطلبات الذرية حتى لا تسقط موافقة إدارية معلقة عند
    إعادة تشغيل منسق العنقود.
    """

    def __init__(
        self,
        persist_path: str | None = None,
        max_age_seconds: float = 900.0,
        audit_path: str | None = None,
    ) -> None:
        self._requests: dict[str, PendingJoinRequest] = {}
        self._lock = threading.RLock()
        self._path = Path(persist_path) if persist_path else None
        self._audit_path = Path(audit_path) if audit_path else (
            Path(f"{persist_path}.audit.jsonl") if persist_path else None
        )
        self._max_age_seconds = max_age_seconds
        if self._max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be greater than zero")
        self._load()

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            records = json.loads(self._path.read_text(encoding="utf-8"))
            now = time.time()
            for record in records:
                request = PendingJoinRequest(**record)
                if request.status == "pending" and now - request.created_at <= self._max_age_seconds:
                    self._requests[request.request_id] = request
                elif request.status == "pending":
                    request.status = "expired"
                    self._requests[request.request_id] = request
                    self._audit("expired", request, "join request TTL elapsed during restart")
            self._persist()
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            self._requests = {}

    def _persist(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        pending = [vars(request) for request in self._requests.values() if request.status == "pending"]
        temporary = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temporary.write_text(json.dumps(pending, sort_keys=True), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self._path)

    def _audit(self, event: str, request: PendingJoinRequest, reason: str = "") -> None:
        if self._audit_path is None:
            return
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "event": event,
            "at": time.time(),
            "request_id": request.request_id,
            "node_id": request.node_id,
            "host": request.host,
            "mtls_port": request.mtls_port,
            "status": request.status,
            "reason": reason,
        }
        with self._audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(self._audit_path, 0o600)

    def _expire_due(self) -> None:
        now = time.time()
        changed = False
        for request in self._requests.values():
            if request.status == "pending" and now - request.created_at > self._max_age_seconds:
                request.status = "expired"
                self._audit("expired", request, "join request TTL elapsed")
                changed = True
        if changed:
            self._persist()

    def create(
        self,
        node_id: str,
        host: str,
        mtls_port: int,
        cert_pem: str,
        signing_pubkey_hex: str,
        component_public_key_hex: str,
        component_created_at: str,
    ) -> PendingJoinRequest:
        with self._lock:
            request_id = f"peer-{uuid.uuid4().hex[:10]}"
            request = PendingJoinRequest(
                request_id=request_id,
                node_id=node_id,
                host=host,
                mtls_port=mtls_port,
                cert_pem=cert_pem,
                signing_pubkey_hex=signing_pubkey_hex,
                component_public_key_hex=component_public_key_hex,
                component_created_at=component_created_at,
            )
            self._requests[request_id] = request
            self._persist()
            self._audit("requested", request)
            return request

    def get(self, request_id: str) -> Optional[PendingJoinRequest]:
        with self._lock:
            self._expire_due()
            return self._requests.get(request_id)

    def list_pending(self) -> list[PendingJoinRequest]:
        with self._lock:
            self._expire_due()
            return [r for r in self._requests.values() if r.status == "pending"]

    def mark_approved(self, request_id: str) -> Optional[PendingJoinRequest]:
        with self._lock:
            self._expire_due()
            request = self._requests.get(request_id)
            if request is not None and request.status == "pending":
                request.status = "approved"
                self._persist()
                self._audit("approved", request)
            return request

    def mark_rejected(self, request_id: str) -> Optional[PendingJoinRequest]:
        with self._lock:
            self._expire_due()
            request = self._requests.get(request_id)
            if request is not None and request.status == "pending":
                request.status = "rejected"
                self._persist()
                self._audit("rejected", request)
            return request
