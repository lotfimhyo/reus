# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas import AgentResponse, RegisterAgentRequest, StateChangeRequest
from application.agent_service import AgentService, RegisterAgentCommand
from container import get_agent_service
from domain.entities import InvalidStateTransition, PermissionDenied
from domain.repositories import AgentNotFound
from infrastructure.security import verify_api_key

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def register_agent(
    body: RegisterAgentRequest,
    service: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    try:
        agent = service.register_agent(
            RegisterAgentCommand(name=body.name, permissions=set(body.permissions), goals=body.goals)
        )
    except PermissionDenied as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AgentResponse.from_domain(agent)


@router.get("", response_model=list[AgentResponse])
def list_agents(service: AgentService = Depends(get_agent_service)) -> list[AgentResponse]:
    return [AgentResponse.from_domain(a) for a in service.list_agents()]


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: str, service: AgentService = Depends(get_agent_service)) -> AgentResponse:
    try:
        return AgentResponse.from_domain(service.get_agent(agent_id))
    except AgentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{agent_id}/state", response_model=AgentResponse)
def change_agent_state(
    agent_id: str,
    body: StateChangeRequest,
    service: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    try:
        agent = service.change_state(agent_id, body.target_state)
    except AgentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AgentResponse.from_domain(agent)
