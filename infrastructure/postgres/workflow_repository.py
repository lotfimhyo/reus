# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
PostgresWorkflowRepository: يخزّن Workflow (Aggregate Root) كمستند JSON واحد.
عند القراءة، يُعاد بناء كائنات TaskNode وWorkflow بالكامل عبر منطق الدومين
(وليس عبر ORM مباشر) حتى تبقى كل قواعد الاتساق (كشف الحلقات إلخ) مطبَّقة كما هي.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from domain.workflow import TaskNode, TaskState, Workflow
from domain.workflow_repository import WorkflowNotFound, WorkflowRepository
from infrastructure.postgres.models import WorkflowModel
from infrastructure.postgres.session import new_session


def _task_to_dict(task: TaskNode) -> dict:
    return {
        "task_id": task.task_id,
        "name": task.name,
        "agent_id": task.agent_id,
        "depends_on": sorted(task.depends_on),
        "max_retries": task.max_retries,
        "payload": task.payload,
        "state": task.state.value,
        "retry_count": task.retry_count,
        "result": task.result,
        "error": task.error,
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def _dict_to_task(d: dict) -> TaskNode:
    return TaskNode(
        name=d["name"],
        agent_id=d["agent_id"],
        depends_on=frozenset(d["depends_on"]),
        max_retries=d["max_retries"],
        payload=d.get("payload", {}),
        task_id=d["task_id"],
        state=TaskState(d["state"]),
        retry_count=d["retry_count"],
        result=d["result"],
        error=d["error"],
        created_at=datetime.fromisoformat(d["created_at"]),
        started_at=datetime.fromisoformat(d["started_at"]) if d["started_at"] else None,
        completed_at=datetime.fromisoformat(d["completed_at"]) if d["completed_at"] else None,
    )


def _workflow_to_document(workflow: Workflow) -> dict:
    return {"tasks": [_task_to_dict(t) for t in workflow.tasks.values()]}


def _row_to_workflow(row: WorkflowModel) -> Workflow:
    tasks = {t["task_id"]: _dict_to_task(t) for t in row.document["tasks"]}
    workflow = Workflow(name=row.name, tasks=tasks, workflow_id=row.workflow_id)
    workflow.created_at = row.created_at
    return workflow


class PostgresWorkflowRepository(WorkflowRepository):
    def add(self, workflow: Workflow) -> None:
        with new_session() as session:
            session.add(
                WorkflowModel(
                    workflow_id=workflow.workflow_id,
                    name=workflow.name,
                    created_at=workflow.created_at,
                    document=_workflow_to_document(workflow),
                )
            )
            session.commit()

    def get(self, workflow_id: str) -> Workflow:
        with new_session() as session:
            row = session.get(WorkflowModel, workflow_id)
            if row is None:
                raise WorkflowNotFound(workflow_id)
            return _row_to_workflow(row)

    def update(self, workflow: Workflow) -> None:
        with new_session() as session:
            row = session.get(WorkflowModel, workflow.workflow_id)
            if row is None:
                raise WorkflowNotFound(workflow.workflow_id)
            row.document = _workflow_to_document(workflow)
            session.commit()

    def list_all(self) -> list[Workflow]:
        with new_session() as session:
            rows = session.execute(select(WorkflowModel)).scalars().all()
            return [_row_to_workflow(r) for r in rows]
