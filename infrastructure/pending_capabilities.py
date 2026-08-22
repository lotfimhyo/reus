"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

PendingCapabilityStore — نفس نمط `infrastructure/cluster_network/
join_requests.py` (`PendingJoinStore`) تمامًا، لسبب واحد متعمَّد: هذا هو
البوابة البشرية الثانية في النظام (الأولى: انضمام عقدة جديدة للعنقود؛
هذه: قدرة جديدة يقترحها نموذج Ollama لعقدة موجودة أصلًا) — نفس الشكل يعني
نفس الضمانات (لا شيء يُعتمَد إلا بقرار بشري صريح عبر تلغرام)، ونفس سهولة
المراجعة لاحقًا.

الفارق الجوهري عن PendingJoinStore: هنا يُخزَّن `BuildResult` كامل (اجتاز
فعلًا كل بوابات الأمان الآلية: توليد → فحص ثابت → sandbox) — وليس مجرد
ادّعاء غير مُتحقَّق منه. الموافقة البشرية هنا ليست بديلًا عن الفحص الآلي، بل
طبقة إضافية فوقه: "هذا الكود آمن آليًا، لكن هل نريده فعلًا في هذه العقدة؟"
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
                "لا يمكن إدراج BuildResult مرفوض في PendingCapabilityStore — "
                "الرفض الآلي نهائي، لا يمرّ للمراجعة البشرية أصلًا."
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
