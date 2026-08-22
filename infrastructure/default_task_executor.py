# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
DefaultTaskExecutor: تطبيق حقيقي (وليس Placeholder) لواجهة TaskExecutor.

قرار هندسي موثّق بصدق: هذه البيئة لا تملك بعد تكامل استدعاء نماذج/أدوات خارجية
(ذلك موضوع حلقة "اختيار النموذج الأنسب" اللاحقة). لذا "تنفيذ المهمة" هنا هو
تكامل فعلي حقيقي بين الوحدات المبنية مسبقًا: يتحقق من صلاحيات الوكيل، يسترجع
سياقًا ذا صلة من ذاكرته الدلالية (إن سُمح له بالقراءة)، وإن سُمح له بالكتابة
يسجّل نتيجة تنفيذ المهمة كمقطع ذاكرة جديد — فيتراكم للوكيل سياق حقيقي عبر
تنفيذ المهام المتعاقبة. هذا سلوك مفيد وحقيقي بحد ذاته (ليس محاكاة فارغة)،
وقابل للاستبدال لاحقًا بمنفّذ يستدعي نموذجًا فعليًا عبر نفس الواجهة (TaskExecutor).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from application.agent_service import AgentService
from application.memory_service import MemoryService, StoreMemoryCommand
from application.task_executor import TaskExecutionError, TaskExecutor
from domain.entities import PermissionDenied
from domain.repositories import AgentNotFound
from domain.workflow import TaskNode

logger = logging.getLogger("reus_veritas.worker")


class DefaultTaskExecutor(TaskExecutor):
    def __init__(self, agent_service: AgentService, memory_service: MemoryService) -> None:
        self._agents = agent_service
        self._memory = memory_service

    def execute(self, task: TaskNode) -> Any:
        if task.agent_id is None:
            if "prompt" in task.payload:
                # اكتُشِف فعليًا عبر تشغيل حي للنظام كاملًا (لا اختبار وحدة —
                # اختبارات /chat تستبدل المنفِّذ بمزيَّف دائمًا، فلا تصطدم بهذا
                # إطلاقًا): REUS_TASK_EXECUTOR="default" هو الإعداد الافتراضي
                # الفعلي في config.py، وDefaultTaskExecutor هذا يتطلب وكيلًا
                # مُسجَّلًا لكل مهمة — لكن /chat لا يُسنِد agent_id لمهامه أبدًا
                # (محادثة عامة عديمة الحالة، لا وكيل مُحدَّد). هذا يعني: نشر
                # افتراضي كامل بلا أي إعداد إضافي يُنتج 502 على /chat من أول
                # طلب. رسالة الخطأ القديمة ("بلا وكيل مُسنَد") كانت صحيحة
                # تقنيًا لكن غير قابلة للتصرف لمن يواجهها فعليًا — لا تشرح
                # السبب الجذري (اختيار منفِّذ التنفيذ) ولا الحل.
                raise TaskExecutionError(
                    "REUS_TASK_EXECUTOR=\"default\" لا يدعم محادثة نصية حرة عبر /chat — "
                    "هذا المنفِّذ يتطلب وكيلًا مُسجَّلًا مسبقًا لكل مهمة، بينما /chat "
                    "عام وعديم الحالة عمدًا. لتفعيل /chat فعليًا، اضبط REUS_TASK_EXECUTOR "
                    "إلى \"ollama\" (يتطلب خادم Ollama محلي، REUS_OLLAMA_ENABLED=true)، "
                    "أو \"model_router\" (يتطلب REUS_ANTHROPIC_API_KEY أو REUS_OPENAI_API_KEY "
                    "أو REUS_GOOGLE_API_KEY). ملاحظة: \"cognitive\" لا يدعم /chat أيضًا — "
                    "يتطلب required_capability_name/required_tags في الحمولة، وهو ما لا "
                    "يُسنِده /chat أبدًا؛ ذلك المنفِّذ مخصَّص لمهام مُوجَّهة لقدرة محدَّدة."
                )
            raise TaskExecutionError(f"المهمة '{task.name}' بلا وكيل مُسنَد؛ لا يمكن تنفيذها")

        try:
            self._agents.get_agent(task.agent_id)
        except AgentNotFound as exc:
            raise TaskExecutionError(str(exc)) from exc

        context: list[str] = []
        try:
            results = self._memory.search(task.agent_id, query=task.name, top_k=3)
            context = [r.record.content for r in results]
        except PermissionDenied:
            logger.info("worker_context_skipped_no_read_permission", extra={"event_name": "worker_context_skipped"})

        summary = f"Task '{task.name}' executed at {datetime.now(timezone.utc).isoformat()}"
        try:
            self._memory.store(
                StoreMemoryCommand(agent_id=task.agent_id, content=summary, tags=["task-execution"])
            )
        except PermissionDenied:
            logger.info("worker_result_not_stored_no_write_permission", extra={"event_name": "worker_result_skipped"})

        return {"task_name": task.name, "agent_id": task.agent_id, "context_used": context, "summary": summary}
