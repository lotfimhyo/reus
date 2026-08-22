# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
ModelRoutingExecutor: تطبيق TaskExecutor يستخدم ModelRouter لاختيار أنسب نموذج
لكل مهمة (عبر أي مزوّد مسجَّل) بناءً على payload المهمة، ثم يستدعيه فعليًا عبر
عميل ذلك المزوّد تحديدًا (ModelClientRegistry)، مع دعم اختياري لـ Tool Use.

يقرأ من task.payload:
- "prompt" (مطلوب): النص المُرسَل للنموذج.
- "required_capabilities" (اختياري): قدرات يجب أن يدعمها النموذج المختار.
- "min_context_tokens" (اختياري).
- "max_input_cost_per_1k_tokens_usd" (اختياري): سقف تكلفة.
- "prefer" (اختياري): "cheapest" | "fastest" | "most_capable" (الافتراضي "cheapest").
- "max_tokens" (اختياري): الحد الأقصى لرموز الاستجابة (الافتراضي 1024).
- "enable_tools" (اختياري، افتراضي false): إن كان صحيحًا، يُشغَّل النموذج بحلقة
  أدوات كاملة (Tool Use) يمكنه خلالها استدعاء أدوات الذاكرة (search_memory/
  store_memory) فعليًا، وأدوات التعاون (create_task/list_agents) إن زُوِّد
  المنفّذ بـ orchestrator وagent_repo عند البناء — فيستطيع الوكيل عندها تفويض
  مهام لنفسه أو لوكيل آخر مباشرة أثناء توليد استجابته (بشرط صلاحية spawn:subagent).
  يتطلب أن يدعم عميل المزوّد المختار invoke_with_tools (Anthropic يدعمه حاليًا).

قابل للاستبدال أو التبديل مع DefaultTaskExecutor عبر container.py (REUS_TASK_EXECUTOR)
دون أي تعديل في TaskWorker أو OrchestratorService.
"""
from __future__ import annotations

from typing import Any

from application.agent_tools import ALL_TOOLS, MEMORY_TOOLS, AgentToolExecutor
from application.memory_service import MemoryService
from application.model_router import ModelRouter, NoSuitableModel, TaskRequirements
from application.orchestrator_service import OrchestratorService
from application.task_executor import TaskExecutionError, TaskExecutor
from domain.repositories import AgentRepository
from domain.workflow import TaskNode
from infrastructure.model_client import ModelInvocationError, ToolUseNotSupported
from infrastructure.model_client_registry import ModelClientRegistry, UnknownProvider


class ModelRoutingExecutor(TaskExecutor):
    def __init__(
        self,
        router: ModelRouter,
        client_registry: ModelClientRegistry,
        memory_service: MemoryService | None = None,
        orchestrator: OrchestratorService | None = None,
        agent_repo: AgentRepository | None = None,
    ) -> None:
        self._router = router
        self._clients = client_registry
        self._memory_service = memory_service
        self._orchestrator = orchestrator
        self._agent_repo = agent_repo

    def execute(self, task: TaskNode) -> Any:
        prompt = task.payload.get("prompt")
        if not prompt:
            raise TaskExecutionError(f"المهمة '{task.name}' بلا 'prompt' في payload؛ لا يمكن توجيهها إلى نموذج")

        requirements = TaskRequirements(
            required_capabilities=frozenset(task.payload.get("required_capabilities", [])),
            min_context_tokens=task.payload.get("min_context_tokens", 0),
            max_input_cost_per_1k_tokens_usd=task.payload.get("max_input_cost_per_1k_tokens_usd"),
            prefer=task.payload.get("prefer", "cheapest"),
        )

        try:
            model = self._router.select(requirements)
        except NoSuitableModel as exc:
            raise TaskExecutionError(str(exc)) from exc

        try:
            client = self._clients.get(model.provider)
        except UnknownProvider as exc:
            raise TaskExecutionError(str(exc)) from exc

        max_tokens = task.payload.get("max_tokens", 1024)

        if task.payload.get("enable_tools"):
            if task.agent_id is None:
                raise TaskExecutionError("استخدام الأدوات (enable_tools) يتطلب إسناد المهمة لوكيل (agent_id)")
            if self._memory_service is None:
                raise TaskExecutionError("استخدام الأدوات يتطلب تزويد ModelRoutingExecutor بـ MemoryService")

            tool_executor = AgentToolExecutor(
                memory_service=self._memory_service,
                agent_id=task.agent_id,
                orchestrator=self._orchestrator,
                agent_repo=self._agent_repo,
            )
            # نعرض أدوات التعاون للنموذج فقط إن كانت مفعّلة فعليًا في هذا المنفّذ،
            # حتى لا يحاول النموذج استدعاء أداة سترفع UnknownTool بلا فائدة
            available_tools = ALL_TOOLS if (self._orchestrator and self._agent_repo) else MEMORY_TOOLS
            try:
                response_text = client.invoke_with_tools(
                    model_id=model.name,
                    prompt=prompt,
                    tools=[t.to_anthropic_format() for t in available_tools],
                    tool_dispatcher=tool_executor.dispatch,
                    max_tokens=max_tokens,
                )
            except (ModelInvocationError, ToolUseNotSupported) as exc:
                raise TaskExecutionError(str(exc)) from exc
        else:
            try:
                response_text = client.invoke(model_id=model.name, prompt=prompt, max_tokens=max_tokens)
            except ModelInvocationError as exc:
                raise TaskExecutionError(str(exc)) from exc

        return {"model_used": model.name, "provider": model.provider, "response": response_text}
