"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

OllamaTaskExecutor — منفّذ المهام الأساسي المطلوب صراحةً: "استدعاء النماذج
المحلية Ollama... مع دعم نماذج API ثانوية". حتى هذه الجلسة، لم يكن يوجد أي
مسار تنفيذ مهام حقيقي يستدعي Ollama مباشرةً للإجابة على مهمة — `OllamaClient`
كان مربوطًا فقط بكتابة كود القدرات (`OllamaSynthesizer`)، لا بالإجابة على
مهام مستخدم فعلية. هذا الملف يسدّ تلك الفجوة تحديدًا.

**العلاقة بـModelRoutingExecutor (النماذج الثانوية):** Ollama هو المسار
الأساسي دائمًا. `ModelRoutingExecutor` (Anthropic/OpenAI/Google) لا يُستدعى
إلا كسقوط تلقائي حقيقي (fallback) عند فشل الوصول لخادم Ollama نفسه
(`OllamaError` — خادم غير مُشغَّل، أو نموذج غير مسحوب محليًا) — وليس كمسار
مستقل يُختار يدويًا كما كان الوضع سابقًا (`REUS_TASK_EXECUTOR=model_router`
يبقى متاحًا كخيار منفصل لمن يريد النماذج الثانوية حصرًا بلا Ollama إطلاقًا).

كل سقوط فعلي (لا كل استدعاء ناجح) يُنشَر على EventBus
(`task.ollama_fallback_used`) — شفافية تشغيلية: يجب أن يكون واضحًا متى
"يتعطّل" النموذج المحلي فعليًا ويُستبدَل مؤقتًا بنموذج API، لا أن يحدث ذلك
بصمت.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from application.task_executor import TaskExecutionError, TaskExecutor
from domain.workflow import TaskNode
from infrastructure.agent_factory.support.ollama_client import OllamaClient, OllamaError
from infrastructure.event_bus import Event, EventBus
from infrastructure.model_promotion import ActiveModelStore

logger = logging.getLogger("reus.ollama_task_executor")


class OllamaTaskExecutor(TaskExecutor):
    def __init__(
        self,
        client: OllamaClient,
        fallback_executor: Optional[TaskExecutor] = None,
        event_bus: Optional[EventBus] = None,
        active_model_store: Optional[ActiveModelStore] = None,
    ) -> None:
        """`fallback_executor` هو عادة `ModelRoutingExecutor` (نماذج API
        ثانوية) — لكن أي `TaskExecutor` آخر صالح أيضًا (بنية قابلة للاستبدال،
        لا اعتماد مباشر على أي مزوّد بعينه). `None` يعني: لا سقوط تلقائي،
        فشل Ollama يفشل المهمة مباشرة — خيار صريح لمن يريد Ollama حصرًا.

        `active_model_store`: إن زُوِّد، يُستشار عند **كل** استدعاء (لا
        عند البناء فقط) لتحديد اسم النموذج الفعلي — هذا ما يجعل قرار
        `ModelPromotionService` (ترقية للنموذج المتطوّر أو التراجع عنها)
        يسري فورًا على أول مهمة تالية، دون إعادة تشغيل هذا المنفّذ أو
        إعادة بناء `OllamaClient`. `None` يعني: استخدم `client.model` الثابت
        دائمًا — خيار صريح لمن لا يريد الترقية إطلاقًا."""
        self._client = client
        self._fallback = fallback_executor
        self._bus = event_bus
        self._active_model_store = active_model_store

    def execute(self, task: TaskNode) -> Any:
        prompt = task.payload.get("prompt")
        if not prompt:
            raise TaskExecutionError(f"المهمة '{task.name}' بلا 'prompt' في payload؛ لا يمكن توجيهها إلى نموذج")

        system = task.payload.get("system")
        json_mode = task.payload.get("json_mode", False)
        model_override = self._active_model_store.get_active() if self._active_model_store else None

        try:
            response_text = self._client.generate(prompt, system=system, json_mode=json_mode, model=model_override)
        except OllamaError as exc:
            return self._fallback_or_raise(task, exc)

        return {
            "model_used": model_override or self._client.model,
            "provider": "ollama",
            "response": response_text,
        }

    def _fallback_or_raise(self, task: TaskNode, original_error: OllamaError) -> Any:
        if self._fallback is None:
            raise TaskExecutionError(
                f"تعذّر الوصول لـ Ollama ولا يوجد منفّذ سقوط تلقائي مُهيَّأ: {original_error}"
            ) from original_error

        logger.warning("ollama_unreachable_falling_back", extra={"task_name": task.name, "error": str(original_error)})
        self._publish(
            "task.ollama_fallback_used",
            {"task_id": task.task_id, "task_name": task.name, "reason": str(original_error)},
        )
        try:
            result = self._fallback.execute(task)
        except TaskExecutionError as exc:
            raise TaskExecutionError(
                f"تعذّر الوصول لـ Ollama ({original_error})، وفشل منفّذ السقوط التلقائي أيضًا: {exc}"
            ) from exc
        except Exception as exc:  # أي خطأ آخر غير متوقَّع من منفّذ السقوط — لا نبتلعه
            raise TaskExecutionError(
                f"تعذّر الوصول لـ Ollama ({original_error})، وفشل منفّذ السقوط التلقائي أيضًا: {exc}"
            ) from exc

        if isinstance(result, dict):
            result = {**result, "fallback_from": "ollama", "fallback_reason": str(original_error)}
        return result

    def _publish(self, name: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(Event(name=name, payload=payload))
