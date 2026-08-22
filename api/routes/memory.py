# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas import (
    MemoryRecordResponse,
    MemorySearchResultResponse,
    SearchMemoryRequest,
    StoreMemoryRequest,
)
from application.memory_service import MemoryService, StoreMemoryCommand
from container import get_memory_service
from domain.entities import PermissionDenied
from domain.memory_repository import MemoryNotFound
from domain.repositories import AgentNotFound
from infrastructure.security import require_agent_scope

# لا يوجد تحقق جماعي على مستوى الموجّه عمدًا: كل مسار يفرض الصلاحية الدقيقة
# التي يحتاجها فعليًا (read:memory أو write:memory)، حتى يُطبَّق نطاق الرمز
# (Token Scope) بدقة لكل عملية على حدة، لا "وصول كامل لكل شيء تحت هذا المسار".
router = APIRouter(prefix="/agents/{agent_id}/memory", tags=["memory"])


@router.post(
    "", response_model=MemoryRecordResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_agent_scope("write:memory"))],
)
def store_memory(
    agent_id: str,
    body: StoreMemoryRequest,
    service: MemoryService = Depends(get_memory_service),
) -> MemoryRecordResponse:
    try:
        record = service.store(StoreMemoryCommand(agent_id=agent_id, content=body.content, tags=body.tags))
    except AgentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return MemoryRecordResponse.from_domain(record)


@router.get(
    "", response_model=list[MemoryRecordResponse],
    dependencies=[Depends(require_agent_scope("read:memory"))],
)
def list_memory(agent_id: str, service: MemoryService = Depends(get_memory_service)) -> list[MemoryRecordResponse]:
    try:
        records = service.list_for_agent(agent_id)
    except AgentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return [MemoryRecordResponse.from_domain(r) for r in records]


@router.post(
    "/search", response_model=list[MemorySearchResultResponse],
    dependencies=[Depends(require_agent_scope("read:memory"))],
)
def search_memory(
    agent_id: str,
    body: SearchMemoryRequest,
    service: MemoryService = Depends(get_memory_service),
) -> list[MemorySearchResultResponse]:
    try:
        results = service.search(agent_id, body.query, top_k=body.top_k)
    except AgentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return [MemorySearchResultResponse.from_domain(r) for r in results]


@router.delete(
    "/{memory_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_agent_scope("write:memory"))],
)
def forget_memory(agent_id: str, memory_id: str, service: MemoryService = Depends(get_memory_service)) -> None:
    try:
        service.forget(agent_id, memory_id)
    except AgentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MemoryNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
