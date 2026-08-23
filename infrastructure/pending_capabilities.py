"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

PendingCapabilityStore deliberately follows the same pattern as
`PendingJoinStore`: it is the system's second human gate. The first governs a
new node joining a cluster; this one governs an Ollama-proposed capability for
an existing node. The shared shape gives the same assurance that nothing is
accepted without explicit human Telegram approval and remains easy to audit.

Unlike PendingJoinStore, this store holds a complete BuildResult that has
already passed automated gates—generation, static review, and sandboxing—not an
unverified claim. Human approval is an additional layer, not a replacement for
automated checks: the code passed the automated safety gates, but is it wanted
on this node?
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from infrastructure.agent_factory.builder import BuildResult


@dataclass
class PendingCapabilityRequest:
    request_id: str
    node_role_id: str
    build_result: BuildResult
    status: str = "pending"  # pending | approved | rejected
    created_at: float = field(default_factory=time.time)


class PendingCapabilityStore:
    def __init__(self) -> None:
        self._requests: dict[str, PendingCapabilityRequest] = {}
        self._lock = threading.RLock()

    def create(self, node_role_id: str, build_result: BuildResult) -> PendingCapabilityRequest:
        if not build_result.approved:
            raise ValueError(
                "A rejected BuildResult cannot enter PendingCapabilityStore; "
                "automated rejection is final and never reaches human review."
            )
        with self._lock:
            request_id = f"cap-{uuid.uuid4().hex[:10]}"
            request = PendingCapabilityRequest(
                request_id=request_id, node_role_id=node_role_id, build_result=build_result
            )
            self._requests[request_id] = request
            return request

    def get(self, request_id: str):
        with self._lock:
            return self._requests.get(request_id)

    def list_pending(self) -> list[PendingCapabilityRequest]:
        with self._lock:
            return [r for r in self._requests.values() if r.status == "pending"]

    def mark_approved(self, request_id: str):
        with self._lock:
            request = self._requests.get(request_id)
            if request is not None:
                request.status = "approved"
            return request

    def mark_rejected(self, request_id: str):
        with self._lock:
            request = self._requests.get(request_id)
            if request is not None:
                request.status = "rejected"
            return request
