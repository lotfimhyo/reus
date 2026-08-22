# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
SecureRemoteExecutor: نفس عقد RemoteExecutor الأصلي ((step, payload) ->
HandlerResult عبر إرسال للعقدة المالكة للقدرة)، لكن بفارق أمني جوهري واحد
مقصود:

RemoteExecutor الأصلي (infrastructure/cognitive_core/cluster/remote_executor.py)
يرسل عبر `requests.post` عاديًا — بلا مصادقة، بلا تشفير نقل، لأي `api_base_url`
مسجَّل في PeerDirectory. هذا يعني أن أي طرف يتحكم بذلك العنوان (انتحال DNS/شبكة)
يستطيع قراءة كل payload يُرسَل، أو إرجاع نتائج مزيَّفة تُعامَل كموثوقة. هذا لا
يتوافق مع بقية النظام الذي يبني بنية mTLS كاملة (TrustStore + SecureNodeClient)
لهذا الغرض بالضبط — لكن RemoteExecutor لم يكن يستخدمها إطلاقًا.

القرار هنا: PeerDirectory يبقى كما هو تمامًا (مسؤوليته الوحيدة والصحيحة: تتبّع
"أي عقدة تملك أي capability_id" — هذا لا علاقة له بالنقل). لكن "أين ولمن نرسل
فعليًا" يُستمَد الآن حصرًا من TrustStore (نفس مصدر ثقة النقل الذي تستخدمه Raft
وDiscoveryService) — عقدة غير موجودة في TrustStore تُرفض صراحة، لا تُرسَل لها
أي بيانات عبر قناة غير موثوقة مهما كانت مسجَّلة في PeerDirectory.

RemoteExecutor الأصلي لم يُحذف — يبقى مفيدًا فقط لاختبار محلي/تطوير حيث
لا شبكة مادية بين "عقد" فعلية. لا يُستخدم أبدًا في نشر حقيقي متعدد العقد؛
راجع الفرق موثّقًا في README.
"""
from __future__ import annotations

from typing import Any

from infrastructure.cluster_network.secure_client import SecureNodeClient
from infrastructure.cluster_network.trust_store import TrustStore
from infrastructure.cognitive_core.cluster.peer_directory import PeerDirectory
from infrastructure.cognitive_core.resource.local_executor import HandlerResult

DEFAULT_TIMEOUT_SECONDS = 30.0


class SecureRemoteExecutor:
    def __init__(
        self,
        peer_directory: PeerDirectory,
        trust_store: TrustStore,
        secure_client: SecureNodeClient,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.peer_directory = peer_directory
        self.trust_store = trust_store
        self.secure_client = secure_client
        self.timeout_seconds = timeout_seconds

    def __call__(self, step: Any, payload: dict) -> HandlerResult:
        node_id = self.peer_directory.capability_origin(step.capability_id)
        if node_id is None:
            return HandlerResult(
                success=False, output={}, error=f"لا عقدة معروفة تملك capability_id={step.capability_id!r}."
            )

        peer = self.trust_store.get_peer(node_id)
        if peer is None:
            # الفرق الأمني الجوهري عن RemoteExecutor: عقدة مسجَّلة في
            # PeerDirectory لكن غير موجودة في TrustStore (غير موثوقة عند
            # طبقة النقل) تُرفَض صراحة، لا تُرسَل لها أي بيانات إطلاقًا.
            return HandlerResult(
                success=False,
                output={},
                error=f"العقدة {node_id!r} غير موجودة في TrustStore — رُفض الإرسال (غير موثوقة عند طبقة النقل).",
            )

        try:
            response = self.secure_client.post_json(
                peer["host"],
                peer["port"],
                "/goals",
                {
                    "description": f"Remote execution of capability {step.name!r}",
                    "required_capability_name": step.name,
                    "payload": payload,
                },
                timeout=self.timeout_seconds,
            )
        except (ConnectionError, OSError, TimeoutError) as exc:
            return HandlerResult(success=False, output={}, error=f"فشل الاتصال الآمن بـ{node_id!r}: {exc}")

        if response is None:
            return HandlerResult(success=False, output={}, error=f"استجابة فارغة من {node_id!r}.")

        return HandlerResult(
            success=bool(response.get("success", False)),
            output=response.get("output", {}) or {},
            error=response.get("error"),
        )
