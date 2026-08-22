"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

CapabilityEvolutionService — يُغلق الحلقة المطلوبة صراحةً: "العقد تطور نفسها
عبر اشراف بشري في تلقرام".

التدفق الكامل (كل خطوة حقيقية، لا محاكاة):
  1. فجوة مهارة تُوصَف (`AgentSpec` بحد أدنى حالة اختبار واحدة يحدّدها من
     يطلب التطوّر — إنسان أو منطق مراقبة لاحق، خارج نطاق هذا الملف).
  2. `OllamaSynthesizer` (نموذج Ollama محلي حقيقي) يكتب المنطق الفعلي.
  3. `IndependentTestReviewer` (استدعاء Ollama منفصل ثانٍ) يقترح حالات
     اختبار إضافية مستقلة — مراجع مختلف عن الكاتب، وليس نفس الاستدعاء الذي
     كتب الكود يراجع نفسه.
  4. `AgentBuilder` (`AgentCapabilityBinder.build()`) يُطبِّق **بلا أي
     استثناء أو تخفيف**: فحص ثابت (بلا imports/eval/dunder) ثم sandbox
     معزول حقيقي (subprocess + حدود موارد) لكل حالات الاختبار مجتمعة.
  5. فقط عند نجاح كل ما سبق: تُدرَج القدرة في `PendingCapabilityStore`
     وتُرسَل إشعارات فورية لكل محادثات الإدارة على تلغرام.
  6. لا شيء يُربَط فعليًا (`bind`) في `CapabilityLayer`/`LocalExecutor`، ولا
     تُضاف القدرة لمهارات `NodeRole`، إلا بعد `/approve_capability` ثم تأكيد
     `/approve` من نفس بوابة `request_approval` المزدوجة المستخدمة لكل قرار
     حساس آخر في هذا النظام (نشر سحابي، ثقة عنقود جديدة).

قدرة يقترحها Ollama ولم تُرفَض آليًا لا تحصل على أي ثقة إضافية لكونها
"اجتازت الفحص" — الفحص الآلي شرط ضروري، لا كافٍ؛ الموافقة البشرية شرط لاحق
منفصل تمامًا، غير قابل للتجاوز.
"""
from __future__ import annotations

import uuid
from typing import Optional

from application.telegram_service import TelegramService
from infrastructure.agent_factory.builder import BuildResult
from infrastructure.agent_factory.manifest import AgentSpec
from infrastructure.capability_binder import AgentCapabilityBinder
from infrastructure.cognitive_core.capability.descriptor import CapabilityDescriptor
from infrastructure.event_bus import Event, EventBus
from infrastructure.node_roles import NODE_ROLES
from infrastructure.pending_capabilities import PendingCapabilityRequest, PendingCapabilityStore


class CapabilityEvolutionService:
    def __init__(
        self,
        binder: AgentCapabilityBinder,
        pending_store: PendingCapabilityStore,
        telegram: TelegramService,
        admin_chat_ids: frozenset[str],
        event_bus: Optional[EventBus] = None,
    ):
        self._binder = binder
        self._pending = pending_store
        self._telegram = telegram
        self._admin_chat_ids = admin_chat_ids
        self._bus = event_bus

        telegram.register_admin_command("/pending_capabilities", self._cmd_pending)
        telegram.register_admin_command("/approve_capability", self._cmd_approve)
        telegram.register_admin_command("/reject_capability", self._cmd_reject)

    # -- الخطوات 1-5: اقتراح + بناء + إشعار ---------------------------------

    def propose_capability(self, node_role_id: str, spec: AgentSpec) -> BuildResult:
        """يبني القدرة عبر البوابات الآلية الكاملة فقط — لا يربطها، ولا
        يفترض شيئًا بشأن قرار بشري لاحق. يُعيد BuildResult دائمًا (لا يرفع
        استثناء) حتى يستطيع المستدعي إظهار سبب الرفض الآلي إن حدث."""
        if node_role_id not in NODE_ROLES:
            raise ValueError(f"دور عقدة غير معروف: {node_role_id!r}")

        result = self._binder.build(spec)
        if not result.approved:
            self._publish(
                "capability.evolution.rejected_automatically",
                {"node_role_id": node_role_id, "reason": result.reason},
            )
            return result

        request = self._pending.create(node_role_id, result)
        self._publish(
            "capability.evolution.pending_review",
            {"request_id": request.request_id, "node_role_id": node_role_id, "capability": spec.capability},
        )
        self._notify_admins(request)
        return result

    def _notify_admins(self, request: PendingCapabilityRequest) -> None:
        spec = request.build_result.spec
        text = (
            f"🧬 اقترح Ollama مهارة جديدة لعقدة '{request.node_role_id}':\n"
            f"المعرّف: {request.request_id}\nالقدرة: {spec.capability}\nالوصف: {spec.description}\n\n"
            f"اجتازت الفحص الآلي الكامل (توليد → فحص ثابت → sandbox). "
            f"للمراجعة: /approve_capability {request.request_id}  أو  /reject_capability {request.request_id}"
        )
        for chat_id in self._admin_chat_ids:
            self._telegram.deliver(chat_id, text)

    # -- أوامر تلغرام (خطوة 6: الإشراف البشري) ------------------------------

    def _cmd_pending(self, chat_id: str, args: str) -> None:
        pending = self._pending.list_pending()
        if not pending:
            self._telegram.deliver(chat_id, "لا توجد مهارات مقترَحة معلّقة.")
            return
        lines = [
            f"- {r.request_id} | عقدة={r.node_role_id} | {r.build_result.spec.capability}" for r in pending
        ]
        self._telegram.deliver(chat_id, "المهارات المقترَحة المعلّقة:\n" + "\n".join(lines))

    def _cmd_approve(self, chat_id: str, args: str) -> None:
        request_id = args.strip()
        request = self._pending.get(request_id)
        if request is None or request.status != "pending":
            self._telegram.deliver(chat_id, f"لا يوجد طلب معلّق بالمعرّف '{request_id}'.")
            return

        spec = request.build_result.spec
        approval_id = f"cap-approve-{uuid.uuid4().hex[:8]}"
        self._telegram.request_approval(
            chat_id,
            approval_id,
            f"ربط مهارة '{spec.capability}' فعليًا بعقدة '{request.node_role_id}' "
            f"(المعرّف: {request_id}). ستصبح قابلة للتنفيذ فورًا بعد الموافقة.",
            on_approve=lambda: self._execute_approve(chat_id, request_id),
            on_reject=lambda: self._telegram.deliver(chat_id, f"أُلغيت مراجعة '{request_id}'."),
        )

    def _execute_approve(self, chat_id: str, request_id: str) -> None:
        request = self._pending.get(request_id)
        if request is None or request.status != "pending":
            self._telegram.deliver(chat_id, f"تعذّر العثور على الطلب '{request_id}' عند التنفيذ.")
            return

        descriptor: CapabilityDescriptor = self._binder.bind(request.build_result)
        role = NODE_ROLES[request.node_role_id]
        # NodeRole مُعرَّف كـ frozen dataclass بحقل specs قابل للتغيير
        # (list عادية) عمدًا — إضافة القدرة المعتمَدة هنا هي بالضبط
        # "تطوّر العقدة لنفسها": مهارتها تكبر بمرور الوقت دون إعادة تعريف
        # NODE_ROLES نفسها في الكود المصدري.
        role.specs.append(request.build_result.spec)

        self._pending.mark_approved(request_id)
        self._publish(
            "capability.evolution.approved",
            {
                "request_id": request_id,
                "node_role_id": request.node_role_id,
                "capability_id": descriptor.capability_id,
            },
        )
        self._telegram.deliver(
            chat_id,
            f"✅ رُبطت المهارة '{descriptor.name}' فعليًا بعقدة '{request.node_role_id}' "
            f"(capability_id={descriptor.capability_id}).",
        )

    def _cmd_reject(self, chat_id: str, args: str) -> None:
        request_id = args.strip()
        request = self._pending.mark_rejected(request_id)
        if request is None:
            self._telegram.deliver(chat_id, f"لا يوجد طلب بالمعرّف '{request_id}'.")
            return
        self._publish("capability.evolution.rejected_by_human", {"request_id": request_id})
        self._telegram.deliver(
            chat_id, f"❌ رُفضت المهارة المقترَحة '{request.build_result.spec.capability}'."
        )

    def _publish(self, name: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(Event(name=name, payload=payload))
