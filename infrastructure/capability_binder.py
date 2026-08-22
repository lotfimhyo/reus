# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
AgentCapabilityBinder: يُغلق الحلقة بين مصنع الوكلاء (AgentBuilder) والنواة
الإدراكية (CapabilityLayer + LocalExecutor).

بدون هذا الملف: AgentBuilder.build() ينجح ويكتب الكود على القرص، لكن لا شيء
يجعله قابلًا للتنفيذ فعليًا عبر REUS_TASK_EXECUTOR=cognitive — القدرة تبقى
"موجودة" على القرص فقط دون أن "تُدرَك".

القاعدة الصارمة هنا: لا تسجيل ولا ربط إلا لـ BuildResult حيث approved=True —
أي أن الكود اجتاز فعلًا: توليد -> فحص ثابت (بلا imports/builtins خطرة) ->
اختبار sandbox معزول لكل حالات الاختبار. هذا الملف لا يُضعف أيًا من تلك
البوابات ولا يتجاوزها؛ فقط يربط ما اجتازها بالفعل.

كل ربط قدرة جديدة عبر هذا المسار يُسجَّل في AppendOnlyAuditLog تلقائيًا
(من خلال CapabilityLayer.publish نفسها) — تتبّع كامل لكل قدرة أضافها النظام
لنفسه، من أين جاءت، ومتى.

بالإضافة لذلك: كل بناء (ناجح أو مرفوض) يُنشَر أيضًا على EventBus المشترك
(capability.built / capability.rejected) — هذا هو الجسر مع ObservabilityService
الموجود أصلًا في Reus (يشترك في "*" على نفس الناقل)، فتظهر قدرات النظام
الذاتية في نفس ملخص المراقبة الموحّد بدل أن تبقى حبيسة سجل تدقيق منفصل لا
يراه أحد إلا بالبحث المباشر فيه.
"""
from __future__ import annotations

from infrastructure.agent_factory.builder import AgentBuilder, BuildResult
from infrastructure.cognitive_core.capability import CapabilityLayer
from infrastructure.cognitive_core.capability.descriptor import CapabilityDescriptor, RiskLevel
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.event_bus import Event, EventBus


class CapabilityBindingRejected(Exception):
    """تُرفَع عندما لا يكون BuildResult معتمدًا — رفض صريح، لا فشل صامت."""


class AgentCapabilityBinder:
    def __init__(
        self,
        builder: AgentBuilder,
        capability_layer: CapabilityLayer,
        local_executor: LocalExecutor,
        component_id: str = "agent_factory",
        default_risk_level: RiskLevel = RiskLevel.LOW,
        event_bus: EventBus | None = None,
    ) -> None:
        self._builder = builder
        self._capabilities = capability_layer
        self._executor = local_executor
        self._component_id = component_id
        self._default_risk_level = default_risk_level
        self._bus = event_bus

    def build_and_bind(self, spec) -> CapabilityDescriptor:
        """يبني القدرة عبر AgentBuilder الكامل (كل بوابات الأمان تُطبَّق كما
        هي)، ثم عند النجاح فقط: يربطها فورًا (bind) دون انتظار أي مراجعة
        إضافية. استُخدم هذا تاريخيًا لكل القدرات المبنية من قوالب معروفة
        (TemplateSynthesizer) — منطق ثابت مكتوب يدويًا، لا حاجة لموافقة
        بشرية إضافية بعد اجتياز البوابات الآلية.

        لقدرات يقترحها نموذج Ollama (OllamaSynthesizer) ضمن حلقة "تطوّر
        العقدة لنفسها"، استخدم `build()` ثم `bind()` منفصلين — انظر
        application/capability_evolution_service.py — حتى تُدرَج خطوة
        موافقة بشرية عبر تلغرام بين الاثنين.

        يرفع CapabilityBindingRejected بنص السبب الكامل من AgentBuilder عند
        أي رفض — لا يُعيد نتيجة صامتة يمكن تجاهلها بالخطأ.
        """
        result: BuildResult = self.build(spec)
        return self.bind(result)

    def build(self, spec) -> BuildResult:
        """الجزء الأول فقط: توليد + فحص ثابت + sandbox، بلا نشر ولا ربط.
        يُعيد BuildResult دومًا (لا يرفع استثناء) — القرار بشأن ما يُفعَل
        بنتيجة مرفوضة متروك للمستدعي (قد يكون: ارفض فورًا، أو أظهر السبب
        لمراجعة بشرية)."""
        result: BuildResult = self._builder.build(spec)
        if not result.approved:
            self._publish(
                "capability.rejected",
                {"spec_name": spec.name, "capability": spec.capability, "reason": result.reason},
            )
        return result

    def bind(self, result: BuildResult) -> CapabilityDescriptor:
        """الجزء الثاني: تحميل الأداة في العملية الحقيقية، نشرها في
        CapabilityLayer، وربط تنفيذها في LocalExecutor. لا يُستدعى إلا على
        BuildResult حيث approved=True — إن استُدعي على نتيجة مرفوضة يرفع
        CapabilityBindingRejected بنفس السبب الأصلي."""
        if not result.approved:
            raise CapabilityBindingRejected(result.reason)

        spec = result.spec
        tool = self._builder.load_tool_instance(result)

        # LocalExecutor يستدعي كل معالج بـ(payload) كاملًا كقاموس دائمًا، بينما
        # أدوات المصنع المولَّدة (run(self, input_data)) تتوقع قيمة خام واحدة.
        # الاتفاقية هنا: القيمة الفعلية تصل عبر مفتاح "input" في payload —
        # موثّقة هنا صراحة بدل ترك الاثنين يتصادمان بصمت.
        #
        # فحص صريح لغياب المفتاح، لا الاعتماد على .get() الصامت: اكتُشِف
        # فعليًا (لا نظريًا) أن استدعاء قدرة نصية (مثل uppercase) بمفتاح
        # مفقود ينتج "NONE" — نتيجة ناجحة ظاهريًا (success=True) لكنها
        # عديمة المعنى فعليًا، لأن str(None).upper() == "NONE" لا يفشل أبدًا.
        # قدرات أخرى (رقمية، int(input_data) مثلًا) كانت سترفع استثناءً
        # مختلفًا تلقائيًا في نفس الحالة — سلوك فشل غير متّسق بين القدرات،
        # يعتمد على تفاصيل قالب كل قدرة بدل ضمان موحَّد. توحيد هذا هنا مرة
        # واحدة لكل القدرات، بدل الاعتماد على سلوك None العرضي لكل قالب.
        def handler(payload: dict, _tool=tool):
            if "input" not in payload:
                raise ValueError(
                    f"القدرة '{spec.capability}' تتطلب مفتاح \"input\" في payload — "
                    f"لم يُرسَل. المفاتيح المُرسَلة فعليًا: {sorted(payload.keys())}"
                )
            return _tool.run(payload["input"])

        descriptor = self._capabilities.publish(
            component_id=self._component_id,
            name=spec.capability,
            description=spec.description,
            input_schema={"input": "any — القيمة الخام المُمرَّرة مباشرة لـ GeneratedTool.run"},
            output_schema={},
            estimated_cost=0.0,
            risk_level=self._default_risk_level,
            tags=("self-built", f"spec:{spec.name}"),
        )
        self._executor.register_handler(descriptor.capability_id, handler)
        self._publish(
            "capability.built",
            {"spec_name": spec.name, "capability": spec.capability, "capability_id": descriptor.capability_id},
        )
        return descriptor

    def _publish(self, name: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(Event(name=name, payload=payload))
