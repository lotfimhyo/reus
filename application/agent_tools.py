# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Application Layer: أدوات الوكيل (Agent Tools).
يحوّل قدرات النظام الحقيقية الموجودة مسبقًا إلى "أدوات" (Tools) بصيغة JSON Schema
يمكن لأي نموذج يدعم Tool Use استدعاءها أثناء توليد استجابته. التنفيذ الفعلي هنا
حقيقي بالكامل — ليس Placeholder:
- أدوات الذاكرة (search_memory, store_memory) تمرّ عبر MemoryService الذي يفرض
  صلاحيات الوكيل (read:memory/write:memory) الموجودة مسبقًا.
- أدوات التعاون (create_task, list_agents) تمرّ عبر OrchestratorService/AgentRepository
  الموجودين مسبقًا، وتفرض صلاحية 'spawn:subagent' (كانت معرَّفة في ALLOWED_PERMISSIONS
  منذ الحلقة الأولى دون استخدام فعلي — هذه أول حلقة تُفعّلها).
لذا لا يمكن لأداة "منح" الوكيل صلاحية لا يملكها أصلًا، في كل الحالتين.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from application.memory_service import MemoryService, StoreMemoryCommand
from application.orchestrator_service import CreateWorkflowCommand, OrchestratorService
from domain.entities import PermissionDenied
from domain.repositories import AgentNotFound, AgentRepository
from domain.workflow import TaskSpec


class UnknownTool(Exception):
    def __init__(self, tool_name: str):
        super().__init__(f"أداة غير معروفة: '{tool_name}'")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict

    def to_anthropic_format(self) -> dict:
        """صيغة الأداة كما تتوقعها Anthropic Messages API (حقل tools)."""
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


SEARCH_MEMORY_TOOL = ToolSpec(
    name="search_memory",
    description="ابحث في ذاكرة الوكيل الدلالية عن مقاطع ذات صلة بموضوع أو سؤال معيّن.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "نص البحث"},
            "top_k": {"type": "integer", "description": "عدد النتائج الأقصى (افتراضيًا 5)"},
        },
        "required": ["query"],
    },
)

STORE_MEMORY_TOOL = ToolSpec(
    name="store_memory",
    description="خزّن معلومة أو ملاحظة جديدة في ذاكرة الوكيل الدلالية لاسترجاعها لاحقًا.",
    input_schema={
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "المحتوى المراد تخزينه"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "وسوم اختيارية للتصنيف"},
        },
        "required": ["content"],
    },
)

MEMORY_TOOLS: list[ToolSpec] = [SEARCH_MEMORY_TOOL, STORE_MEMORY_TOOL]


CREATE_TASK_TOOL = ToolSpec(
    name="create_task",
    description=(
        "أنشئ مهمة جديدة تُنفَّذ فعليًا عبر منسّق المهام في النظام. يمكن إسنادها لنفس "
        "الوكيل (تخطيط ذاتي متعدد الخطوات) أو لوكيل آخر بمعرّفه (تفويض/تعاون حقيقي "
        "بين وكلاء متعددين). تتطلب صلاحية 'spawn:subagent'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task_name": {"type": "string", "description": "اسم مختصر يصف المهمة"},
            "prompt": {"type": "string", "description": "التعليمة/الطلب الذي سيُنفَّذ كمهمة"},
            "target_agent_id": {
                "type": "string",
                "description": "معرّف الوكيل الذي سينفّذ المهمة. اتركه فارغًا لتكليف نفس الوكيل الحالي.",
            },
        },
        "required": ["task_name", "prompt"],
    },
)

LIST_AGENTS_TOOL = ToolSpec(
    name="list_agents",
    description="اعرض قائمة الوكلاء المتاحين في النظام (المعرّف، الاسم، الحالة) لاختيار من يُفوَّض إليه التعاون. تتطلب صلاحية 'spawn:subagent'.",
    input_schema={"type": "object", "properties": {}, "required": []},
)

COLLABORATION_TOOLS: list[ToolSpec] = [CREATE_TASK_TOOL, LIST_AGENTS_TOOL]

ALL_TOOLS: list[ToolSpec] = MEMORY_TOOLS + COLLABORATION_TOOLS


class AgentToolExecutor:
    """
    ينفّذ استدعاء أداة فعليًا نيابة عن وكيل محدد. يُبنى مرة واحدة لكل طلب توجيه
    (مقيَّد بـ agent_id واحد)، حتى لا تحتاج كل أداة لتمرير agent_id بنفسها —
    وهذا يمنع أيضًا أي محاولة (عبر خطأ في النموذج أو تلاعب) لتمرير agent_id مختلف.

    orchestrator وagent_repo اختياريان: إن لم يُمرَّرا (None)، تبقى أدوات الذاكرة
    فقط متاحة، وتُرفع UnknownTool عند محاولة استخدام create_task/list_agents —
    حتى لا يُفترض ضمنيًا وجود منسّق مهام في كل سياق يستخدم أدوات الذاكرة فقط.
    """

    def __init__(
        self,
        memory_service: MemoryService,
        agent_id: str,
        orchestrator: OrchestratorService | None = None,
        agent_repo: AgentRepository | None = None,
    ) -> None:
        self._memory_service = memory_service
        self._agent_id = agent_id
        self._orchestrator = orchestrator
        self._agent_repo = agent_repo

    def dispatch(self, tool_name: str, tool_input: dict) -> dict[str, Any]:
        handler = self._handlers().get(tool_name)
        if handler is None:
            raise UnknownTool(tool_name)
        return handler(tool_input)

    def _handlers(self) -> dict[str, Callable[[dict], dict[str, Any]]]:
        handlers: dict[str, Callable[[dict], dict[str, Any]]] = {
            "search_memory": self._search_memory,
            "store_memory": self._store_memory,
        }
        if self._orchestrator is not None and self._agent_repo is not None:
            handlers["create_task"] = self._create_task
            handlers["list_agents"] = self._list_agents
        return handlers

    def _search_memory(self, tool_input: dict) -> dict[str, Any]:
        try:
            results = self._memory_service.search(
                agent_id=self._agent_id,
                query=tool_input.get("query", ""),
                top_k=tool_input.get("top_k", 5),
            )
        except (PermissionDenied, AgentNotFound) as exc:
            return {"error": str(exc)}
        return {
            "matches": [
                {"memory_id": r.record.memory_id, "content": r.record.content, "score": r.score} for r in results
            ]
        }

    def _store_memory(self, tool_input: dict) -> dict[str, Any]:
        try:
            record = self._memory_service.store(
                StoreMemoryCommand(
                    agent_id=self._agent_id,
                    content=tool_input.get("content", ""),
                    tags=tool_input.get("tags", []),
                )
            )
        except (PermissionDenied, AgentNotFound) as exc:
            return {"error": str(exc)}
        return {"memory_id": record.memory_id, "status": "stored"}

    def _require_spawn_permission(self) -> dict[str, Any] | None:
        """يُعيد dict خطأ جاهزًا للإرجاع مباشرة إن كانت الصلاحية مفقودة، أو None إن كانت متوفرة."""
        try:
            agent = self._agent_repo.get(self._agent_id)
        except AgentNotFound as exc:
            return {"error": str(exc)}
        if "spawn:subagent" not in agent.permissions:
            return {"error": f"الوكيل '{self._agent_id}' لا يملك صلاحية 'spawn:subagent' اللازمة لهذه الأداة"}
        return None

    def _create_task(self, tool_input: dict) -> dict[str, Any]:
        denial = self._require_spawn_permission()
        if denial is not None:
            return denial

        target_agent_id = tool_input.get("target_agent_id") or self._agent_id
        task_name = tool_input.get("task_name", "delegated-task")
        prompt = tool_input.get("prompt", "")

        try:
            workflow = self._orchestrator.create_workflow(
                CreateWorkflowCommand(
                    name=f"tool:{self._agent_id}:{task_name}",
                    tasks=[TaskSpec(name=task_name, agent_id=target_agent_id, payload={"prompt": prompt})],
                )
            )
        except AgentNotFound as exc:
            return {"error": str(exc)}

        task_id = next(iter(workflow.tasks.keys()))
        return {
            "workflow_id": workflow.workflow_id,
            "task_id": task_id,
            "assigned_to": target_agent_id,
            "status": "created",
        }

    def _list_agents(self, tool_input: dict) -> dict[str, Any]:
        denial = self._require_spawn_permission()
        if denial is not None:
            return denial

        agents = self._agent_repo.list_all()
        return {"agents": [{"agent_id": a.agent_id, "name": a.name, "state": a.state.value} for a in agents]}
