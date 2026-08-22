"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

ModelPromotionService — يُغلق الحلقة المطلوبة: "استبدال نموذج الاستخدام
بالنموذج المتطوّر عند نضجه"، بقرار بشري عبر تلغرام لا آلي أبدًا.

**معايير النضج (`evaluate_readiness`) — صادقة وقابلة للتعديل، لا "ذكاء"
مزعوم:**
1. عدد أمثلة التدريب المتراكمة فعليًا >= حد أدنى (`min_examples`، قابل
   للضبط — القيمة الافتراضية صغيرة عمدًا لتكون قابلة للتحقق، يجب على أي
   تشغيل إنتاجي حقيقي رفعها لعدد أكبر بكثير قبل الوثوق بالمعيار).
2. آخر محاولة بناء فعلية للنموذج المتطوّر (`LocalModelBuilder.last_build`)
   نجحت — لا وعد بأن البناء "سينجح"، بل دليل من محاولة حقيقية سابقة.
3. **لا توجد أي قدرة مُمثَّلة في بيانات التدريب حصلت على تقييم موثوقية
   سلبي متعلَّم** (`LearningLayer.score_adjustment` بعد `learn_from_
   capability` فعلي لكل قدرة — لا قيمة افتراضية 0.0 غير مُراجَعة). إن أثبت
   الاستخدام الفعلي أن قدرة ما غير موثوقة، النموذج المبني على أمثلتها لا
   يُعتبَر ناضجًا بغض النظر عن أي معيار آخر.

استيفاء هذه المعايير الثلاثة **لا يُرقّي شيئًا تلقائيًا** — فقط يسمح
بإظهار زر الترقية للإدارة (`/promote_model`)، ولا شيء يتغيّر فعليًا في
`ActiveModelStore` إلا بعد تأكيد بشري مزدوج (`request_approval`، نفس بوابة
كل قرار حسّاس آخر في هذا النظام). التراجع (`/demote_model`) لا يتطلب نفس
معايير النضج — إجراء أمان يجب أن يبقى سهلًا دائمًا.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from application.telegram_service import TelegramService
from infrastructure.cognitive_core.cognitive.learning import LearningLayer
from infrastructure.event_bus import Event, EventBus
from infrastructure.model_promotion import ActiveModelStore
from infrastructure.model_training.local_model_builder import LocalModelBuilder
from infrastructure.model_training.training_dataset import TrainingDatasetStore

# يطابق طيف العقوبات في reliability_advisor.py؛ أي قيمة أسوأ من هذا تعني
# "غير موثوق فعليًا"، لا مجرد نقص بيانات (القيمة المحايدة 0.0).
_UNRELIABLE_THRESHOLD = -1.0


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    total_examples: int
    min_examples: int
    last_build_succeeded: Optional[bool]
    unreliable_capabilities: list[str]

    def reason_ar(self) -> str:
        if self.ready:
            return "كل معايير النضج مستوفاة."
        reasons = []
        if self.total_examples < self.min_examples:
            reasons.append(f"أمثلة التدريب ({self.total_examples}) أقل من الحد الأدنى ({self.min_examples})")
        if self.last_build_succeeded is not True:
            reasons.append("لم ينجح آخر بناء فعلي للنموذج المتطوّر بعد")
        if self.unreliable_capabilities:
            reasons.append(f"قدرات ثبت عدم موثوقيتها فعليًا: {', '.join(self.unreliable_capabilities)}")
        return "؛ ".join(reasons)


class ModelPromotionService:
    def __init__(
        self,
        dataset: TrainingDatasetStore,
        learning: LearningLayer,
        model_builder: LocalModelBuilder,
        active_model_store: ActiveModelStore,
        telegram: TelegramService,
        admin_chat_ids: frozenset[str],
        evolved_model_name: str,
        min_examples: int = 20,
        event_bus: Optional[EventBus] = None,
    ):
        self._dataset = dataset
        self._learning = learning
        self._model_builder = model_builder
        self._active_model_store = active_model_store
        self._telegram = telegram
        self._admin_chat_ids = admin_chat_ids
        self._evolved_model_name = evolved_model_name
        self._min_examples = min_examples
        self._bus = event_bus
        self._already_notified = False

        telegram.register_admin_command("/model_status", self._cmd_status)
        telegram.register_admin_command("/promote_model", self._cmd_promote)
        telegram.register_admin_command("/demote_model", self._cmd_demote)

    def evaluate_readiness(self) -> ReadinessReport:
        total_examples = self._dataset.count()
        last_build = self._model_builder.last_build
        last_build_succeeded = last_build.success if last_build is not None else None

        unreliable: list[str] = []
        for capability_name, examples in self._dataset.examples_by_capability().items():
            capability_id = examples[0].capability_id if examples else None
            if not capability_id:
                continue
            # يُحدَّث دائمًا من أحدث البيانات، لا قيمة مخزَّنة قديمة.
            self._learning.learn_from_capability(capability_id)
            if self._learning.score_adjustment(capability_id) < _UNRELIABLE_THRESHOLD:
                unreliable.append(capability_name)

        ready = total_examples >= self._min_examples and last_build_succeeded is True and not unreliable
        return ReadinessReport(
            ready=ready,
            total_examples=total_examples,
            min_examples=self._min_examples,
            last_build_succeeded=last_build_succeeded,
            unreliable_capabilities=unreliable,
        )

    def notify_if_newly_ready(self) -> None:
        """يُستدعى دوريًا (مثلًا من DailyReportService بعد كل حصاد) — يُرسل
        إشعارًا **مرة واحدة فقط** لكل انتقال من غير-جاهز إلى جاهز، حتى لا
        تُغرَق الإدارة برسالة يومية متكررة لقرار لم يتغيّر. `_already_notified`
        يُعاد ضبطه تلقائيًا إن عاد النموذج غير جاهز حتى يُخطِر مجددًا عند
        نضجه لاحقًا من جديد."""
        report = self.evaluate_readiness()
        if not report.ready:
            self._already_notified = False
            return
        if self._already_notified or self._active_model_store.is_promoted():
            return

        self._already_notified = True
        for chat_id in self._admin_chat_ids:
            self._telegram.deliver(
                chat_id,
                "🧬 النموذج المتطوّر بلغ معايير النضج المُعرَّفة (راجع /model_status للتفاصيل).\n"
                "للترقية الفعلية كنموذج استخدام أساسي: /promote_model\n"
                "الترقية تسري فورًا على أول مهمة تالية دون إعادة تشغيل.",
            )

    def _cmd_status(self, chat_id: str, args: str) -> None:
        report = self.evaluate_readiness()
        active = self._active_model_store.get_active()
        lines = [
            f"النموذج النشط حاليًا: {active}",
            f"مُرقّى؟ {'نعم' if self._active_model_store.is_promoted() else 'لا'}",
            f"أمثلة التدريب المتراكمة: {report.total_examples} (الحد الأدنى: {report.min_examples})",
            f"آخر بناء ناجح؟ {report.last_build_succeeded}",
            f"جاهز للترقية؟ {'نعم' if report.ready else 'لا — ' + report.reason_ar()}",
        ]
        self._telegram.deliver(chat_id, "\n".join(lines))

    def _cmd_promote(self, chat_id: str, args: str) -> None:
        # يُعاد التحقق هنا دومًا — لا يُعتمَد على فحص سابق قد يكون تقادَم.
        report = self.evaluate_readiness()
        if not report.ready:
            self._telegram.deliver(chat_id, f"❌ النموذج المتطوّر غير جاهز للترقية بعد: {report.reason_ar()}")
            return

        approval_id = f"model-promote-{uuid.uuid4().hex[:8]}"
        self._telegram.request_approval(
            chat_id,
            approval_id,
            f"ترقية نموذج الاستخدام الأساسي من النموذج الحالي إلى '{self._evolved_model_name}'. "
            f"ستسري فورًا على كل مهمة تالية عبر Ollama.",
            on_approve=lambda: self._execute_promote(chat_id),
            on_reject=lambda: self._telegram.deliver(chat_id, "أُلغيت الترقية."),
        )

    def _execute_promote(self, chat_id: str) -> None:
        self._active_model_store.set_active(self._evolved_model_name)
        self._publish("model.promoted", {"model_name": self._evolved_model_name})
        self._telegram.deliver(chat_id, f"✅ رُقّي نموذج الاستخدام إلى '{self._evolved_model_name}' فعليًا.")

    def _cmd_demote(self, chat_id: str, args: str) -> None:
        if not self._active_model_store.is_promoted():
            self._telegram.deliver(chat_id, "النموذج النشط بالفعل هو النموذج الأساسي — لا شيء للتراجع عنه.")
            return
        previous = self._active_model_store.get_active()
        self._active_model_store.reset_to_base()
        self._already_notified = False  # يسمح بإشعار جديد إن نضج النموذج مرة أخرى لاحقًا
        self._publish("model.demoted", {"previous_model_name": previous})
        self._telegram.deliver(chat_id, f"↩️ أُعيد نموذج الاستخدام إلى '{self._active_model_store.base_model}'.")

    def _publish(self, name: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(Event(name=name, payload=payload))
