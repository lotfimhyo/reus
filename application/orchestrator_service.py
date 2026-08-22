# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Application Layer: OrchestratorService.
ينسّق دورة حياة الـ Workflow/المهام، يتحقق من وجود الوكيل المُسنَد إليه كل مهمة (إن وُجد)،
وينشر حدثًا لكل تغيير حالة (Event-Driven) ليتمكن أي مكوّن آخر (مراقبة، تنبيهات) من الاشتراك دونما اقتران مباشر.

قاعدة حرجة تُطبَّق في كل دالة هنا: **كل تعديل على حالة Workflow يُحفَظ في المستودع
(add/update) قبل نشر أي حدث متعلق به.** السبب: مع عامل تنفيذ حقيقي (TaskWorker)
يستهلك الأحداث في خيط منفصل فور نشرها، لو نُشر الحدث قبل اكتمال الحفظ، قد يقرأ
العامل حالة قديمة من المستودع (خصوصًا مع PostgreSQL حيث القراءة تُعيد بناء الكائن
من الصف المخزَّن) فتفشل معاملته بخطأ حالة غير صالحة. اكتُشفت هذه المشكلة فعليًا
عبر اختبار "معالجة مهام متعددة بالتزامن" في test_task_worker.py (راجع README).
"""
from __future__ import annotations

from dataclasses import dataclass

from domain.repositories import AgentRepository
from domain.workflow import TaskNode, TaskSpec, Workflow
from domain.workflow_repository import WorkflowRepository
from infrastructure.event_bus import Event, EventBus


@dataclass
class CreateWorkflowCommand:
    name: str
    tasks: list[TaskSpec]


class OrchestratorService:
    def __init__(self, workflow_repo: WorkflowRepository, agent_repo: AgentRepository, event_bus: EventBus) -> None:
        self._workflows = workflow_repo
        self._agents = agent_repo
        self._bus = event_bus

    def create_workflow(self, cmd: CreateWorkflowCommand) -> Workflow:
        for spec in cmd.tasks:
            if spec.agent_id is not None:
                self._agents.get(spec.agent_id)  # يرفع AgentNotFound إن لم يكن موجودًا

        workflow = Workflow.create(name=cmd.name, specs=cmd.tasks)
        promoted = self._mark_ready_tasks(workflow)  # يُعدّل الكائن في الذاكرة فقط، دون نشر أي حدث بعد
        self._workflows.add(workflow)  # يُحفَظ بحالته الكاملة (شاملة أي مهام جاهزة) دفعة واحدة

        self._publish_ready_events(workflow.workflow_id, promoted)
        self._bus.publish(Event(name="workflow.created", payload={"workflow_id": workflow.workflow_id}))
        return workflow

    def get_workflow(self, workflow_id: str) -> Workflow:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[Workflow]:
        return self._workflows.list_all()

    def get_ready_tasks(self, workflow_id: str) -> list[TaskNode]:
        workflow = self._workflows.get(workflow_id)
        return [t for t in workflow.tasks.values() if t.state.value == "ready"]

    def start_task(self, workflow_id: str, task_id: str) -> TaskNode:
        workflow = self._workflows.get(workflow_id)
        node = workflow.start_task(task_id)
        self._workflows.update(workflow)
        self._bus.publish(Event(name="task.started", payload={"workflow_id": workflow_id, "task_id": task_id}))
        return node

    def complete_task(self, workflow_id: str, task_id: str, result=None) -> Workflow:
        workflow = self._workflows.get(workflow_id)
        workflow.complete_task(task_id, result=result)
        promoted = self._mark_ready_tasks(workflow)
        self._workflows.update(workflow)  # يُحفَظ الإكمال + أي ترقية جاهزية معًا قبل أي نشر

        self._bus.publish(Event(name="task.completed", payload={"workflow_id": workflow_id, "task_id": task_id}))
        self._publish_ready_events(workflow_id, promoted)
        if workflow.is_complete():
            self._bus.publish(Event(name="workflow.completed", payload={"workflow_id": workflow_id}))
        return workflow

    def fail_task(self, workflow_id: str, task_id: str, error: str) -> Workflow:
        workflow = self._workflows.get(workflow_id)
        node, cancelled = workflow.fail_task(task_id, error=error)

        promoted: list[TaskNode] = []
        is_retry = node.state.value == "pending"
        if is_retry:
            # أُعيدت المهمة تلقائيًا لإعادة المحاولة (إصلاح ذاتي) — قد تصبح جاهزة فورًا إن لم يكن لها تبعيات
            promoted = self._mark_ready_tasks(workflow)

        self._workflows.update(workflow)  # يُحفَظ الفشل/إعادة المحاولة + أي ترقية جاهزية قبل أي نشر

        if is_retry:
            self._bus.publish(
                Event(
                    name="task.retrying",
                    payload={"workflow_id": workflow_id, "task_id": task_id, "attempt": node.retry_count},
                )
            )
            self._publish_ready_events(workflow_id, promoted)
        else:
            self._bus.publish(
                Event(name="task.failed", payload={"workflow_id": workflow_id, "task_id": task_id, "error": error})
            )
            for c in cancelled:
                self._bus.publish(
                    Event(
                        name="task.cancelled",
                        payload={
                            "workflow_id": workflow_id,
                            "task_id": c.task_id,
                            "reason": f"upstream_failure:{task_id}",
                        },
                    )
                )
            self._bus.publish(Event(name="workflow.failed", payload={"workflow_id": workflow_id, "task_id": task_id}))

        return workflow

    def _mark_ready_tasks(self, workflow: Workflow) -> list[TaskNode]:
        """يُعدّل حالة المهام الجاهزة في الذاكرة فقط، ويُعيدها؛ لا يُنشر أي حدث هنا عمدًا."""
        promoted = []
        for node in workflow.ready_tasks():
            workflow.mark_ready(node.task_id)
            promoted.append(node)
        return promoted

    def _publish_ready_events(self, workflow_id: str, nodes: list[TaskNode]) -> None:
        for node in nodes:
            self._bus.publish(Event(name="task.ready", payload={"workflow_id": workflow_id, "task_id": node.task_id}))
