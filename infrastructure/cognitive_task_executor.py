# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
CognitiveTaskExecutor: يربط TaskNode (طبقة orchestration في Reus-Veritas OS)
بدورة CognitiveEngine الإدراكية (تحليل -> خطط مرشّحة -> تقييم تكلفة/مخاطر ->
تنفيذ -> تعلّم) القادمة من المكوّن المنقول في cognitive_core/.

القرار المعماري هنا: OrchestratorService/TaskWorker يبقيان مسؤولين فقط عن DAG
المهام (تبعيات، إعادة محاولة، أحداث) — وهي مسؤولية Reus الأصلية ولم تتغيّر.
CognitiveEngine مسؤول فقط عن "كيف تُنفَّذ مهمة واحدة" عبر سجل القدرات
(CapabilityRegistry): أي منطق اختيار/تقييم/تعلّم يبقى بالكامل داخل
cognitive_core كما هو، دون إعادة كتابة.

مهمة (TaskNode) تُترجَم إلى Goal عبر payload:
  payload["required_capability_name"] أو payload["required_tags"]
  (مطلوب أحدهما على الأقل، وإلا تُرفض المهمة بخطأ تنفيذ واضح بدل فشل صامت)

مفتاحا التوجيه أعلاه لا يصلان للمعالج (handler) نفسه — CognitiveEngine يمرّر
goal.payload كاملًا لأي معالج دون تمييز بين حقول التوجيه وحقل الإدخال
الفعلي؛ لو تُركا كما هما لتلوّث كل قدرة ذاتية البناء بحقول لا علاقة لها بها.
لذلك يُبنى Goal.payload هنا من الحقول المتبقية بعد استخراج حقلي التوجيه
فقط، فتصل القدرة إلى ما يخصها حصرًا.
"""
from __future__ import annotations

from application.task_executor import TaskExecutionError, TaskExecutor
from domain.workflow import TaskNode
from infrastructure.cognitive_core.cognitive.engine import CognitiveEngine
from infrastructure.cognitive_core.cognitive.exceptions import (
    EmptyPlanSetError,
    NoCapabilityFoundError,
)
from infrastructure.cognitive_core.cognitive.goal import Goal

_ROUTING_KEYS = ("required_capability_name", "required_tags")


class CognitiveTaskExecutor(TaskExecutor):
    """يوصل TaskWorker/OrchestratorService بمحرك Veritas الإدراكي بدل التنفيذ
    الافتراضي البسيط (DefaultTaskExecutor) أو التوجيه المباشر للنموذج
    (ModelRoutingExecutor). يُفعَّل عبر REUS_TASK_EXECUTOR=cognitive.
    """

    def __init__(self, engine: CognitiveEngine, executor) -> None:
        self._engine = engine
        self._executor = executor  # veritas_ai.cognitive.execution.Executor المُحقَن

    def execute(self, task: TaskNode):
        goal = self._build_goal(task)
        try:
            cycle = self._engine.run(goal, self._executor)
        except (NoCapabilityFoundError, EmptyPlanSetError) as exc:
            raise TaskExecutionError(str(exc)) from exc

        if not cycle.execution_result.success:
            raise TaskExecutionError(
                cycle.execution_result.error or f"فشل تنفيذ القدرة المختارة للمهمة {task.task_id}"
            )
        return cycle.execution_result.output

    @staticmethod
    def _build_goal(task: TaskNode) -> Goal:
        required_name = task.payload.get("required_capability_name")
        required_tags = tuple(task.payload.get("required_tags", ()))
        if not required_name and not required_tags:
            raise TaskExecutionError(
                f"مهمة {task.task_id!r} ({task.name!r}) لا تحدد "
                "required_capability_name ولا required_tags في payload — "
                "لا يمكن لـ CognitiveEngine مطابقتها بأي قدرة."
            )
        clean_payload = {k: v for k, v in task.payload.items() if k not in _ROUTING_KEYS}
        return Goal(
            description=task.name,
            payload=clean_payload,
            required_capability_name=required_name,
            required_tags=required_tags,
            goal_id=task.task_id,
        )
