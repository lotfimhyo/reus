# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas_workflow import (
    CompleteTaskRequest,
    CreateWorkflowRequest,
    FailTaskRequest,
    TaskResponse,
    WorkflowResponse,
)
from application.orchestrator_service import CreateWorkflowCommand, OrchestratorService
from container import get_orchestrator_service
from domain.repositories import AgentNotFound
from domain.workflow import CycleDetected, InvalidDependency, InvalidTaskTransition, TaskNotFound, TaskSpec
from domain.workflow_repository import WorkflowNotFound
from infrastructure.security import verify_api_key

router = APIRouter(prefix="/workflows", tags=["orchestrator"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_workflow(
    body: CreateWorkflowRequest,
    service: OrchestratorService = Depends(get_orchestrator_service),
) -> WorkflowResponse:
    specs = [
        TaskSpec(
            name=t.name, agent_id=t.agent_id, depends_on=t.depends_on, max_retries=t.max_retries, payload=t.payload
        )
        for t in body.tasks
    ]
    try:
        workflow = service.create_workflow(CreateWorkflowCommand(name=body.name, tasks=specs))
    except AgentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (CycleDetected, InvalidDependency) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return WorkflowResponse.from_domain(workflow)


@router.get("", response_model=list[WorkflowResponse])
def list_workflows(service: OrchestratorService = Depends(get_orchestrator_service)) -> list[WorkflowResponse]:
    return [WorkflowResponse.from_domain(w) for w in service.list_workflows()]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str, service: OrchestratorService = Depends(get_orchestrator_service)) -> WorkflowResponse:
    try:
        return WorkflowResponse.from_domain(service.get_workflow(workflow_id))
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{workflow_id}/ready-tasks", response_model=list[TaskResponse])
def get_ready_tasks(
    workflow_id: str, service: OrchestratorService = Depends(get_orchestrator_service)
) -> list[TaskResponse]:
    try:
        tasks = service.get_ready_tasks(workflow_id)
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [TaskResponse.from_domain(t) for t in tasks]


@router.post("/{workflow_id}/tasks/{task_id}/start", response_model=TaskResponse)
def start_task(
    workflow_id: str, task_id: str, service: OrchestratorService = Depends(get_orchestrator_service)
) -> TaskResponse:
    try:
        node = service.start_task(workflow_id, task_id)
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TaskNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidTaskTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return TaskResponse.from_domain(node)


@router.post("/{workflow_id}/tasks/{task_id}/complete", response_model=WorkflowResponse)
def complete_task(
    workflow_id: str,
    task_id: str,
    body: CompleteTaskRequest,
    service: OrchestratorService = Depends(get_orchestrator_service),
) -> WorkflowResponse:
    try:
        workflow = service.complete_task(workflow_id, task_id, result=body.result)
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TaskNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidTaskTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return WorkflowResponse.from_domain(workflow)


@router.post("/{workflow_id}/tasks/{task_id}/fail", response_model=WorkflowResponse)
def fail_task(
    workflow_id: str,
    task_id: str,
    body: FailTaskRequest,
    service: OrchestratorService = Depends(get_orchestrator_service),
) -> WorkflowResponse:
    try:
        workflow = service.fail_task(workflow_id, task_id, error=body.error)
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TaskNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidTaskTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return WorkflowResponse.from_domain(workflow)
