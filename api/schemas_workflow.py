# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.workflow import TaskNode, TaskState, Workflow


class TaskSpecRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    agent_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)  # أسماء مهام أخرى ضمن نفس الطلب
    max_retries: int = Field(default=0, ge=0, le=10)
    payload: dict = Field(default_factory=dict)  # مثل {"prompt": "...", "required_capabilities": ["reasoning"]}


class CreateWorkflowRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    tasks: list[TaskSpecRequest] = Field(min_length=1)


class CompleteTaskRequest(BaseModel):
    result: Any = None


class FailTaskRequest(BaseModel):
    error: str = Field(min_length=1, max_length=2000)


class TaskResponse(BaseModel):
    task_id: str
    name: str
    agent_id: str | None
    depends_on: list[str]
    payload: dict
    state: TaskState
    retry_count: int
    max_retries: int
    result: Any
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def from_domain(cls, node: TaskNode) -> "TaskResponse":
        return cls(
            task_id=node.task_id,
            name=node.name,
            agent_id=node.agent_id,
            depends_on=sorted(node.depends_on),
            payload=node.payload,
            state=node.state,
            retry_count=node.retry_count,
            max_retries=node.max_retries,
            result=node.result,
            error=node.error,
            started_at=node.started_at,
            completed_at=node.completed_at,
        )


class WorkflowResponse(BaseModel):
    workflow_id: str
    name: str
    created_at: datetime
    is_complete: bool
    has_permanent_failure: bool
    tasks: list[TaskResponse]

    @classmethod
    def from_domain(cls, workflow: Workflow) -> "WorkflowResponse":
        return cls(
            workflow_id=workflow.workflow_id,
            name=workflow.name,
            created_at=workflow.created_at,
            is_complete=workflow.is_complete(),
            has_permanent_failure=workflow.has_permanent_failure(),
            tasks=[TaskResponse.from_domain(t) for t in workflow.tasks.values()],
        )
