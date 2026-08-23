# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas_agent_token import AgentTokenResponse, IssuedTokenResponse, IssueTokenRequest
from application.agent_token_service import AgentTokenService
from container import get_agent_token_service
from domain.agent_token import ScopeExceedsAgentPermissions
from domain.agent_token_repository import AgentTokenNotFound
from domain.repositories import AgentNotFound
from infrastructure.security import verify_api_key

# Issuing or revoking an agent token is inherently administrative because it
# grants authority; protect it with the primary API key, not an agent token that could self-escalate.
router = APIRouter(prefix="/agents/{agent_id}/tokens", tags=["agent-tokens"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=IssuedTokenResponse, status_code=status.HTTP_201_CREATED)
def issue_token(
    agent_id: str,
    body: IssueTokenRequest,
    service: AgentTokenService = Depends(get_agent_token_service),
) -> IssuedTokenResponse:
    scopes = set(body.scopes) if body.scopes is not None else None
    try:
        issued = service.issue_token(agent_id, label=body.label, scopes=scopes)
    except AgentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScopeExceedsAgentPermissions as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return IssuedTokenResponse(
        token_id=issued.token.token_id,
        plaintext=issued.plaintext,
        label=issued.token.label,
        scopes=sorted(issued.token.scopes),
        created_at=issued.token.created_at,
    )


@router.get("", response_model=list[AgentTokenResponse])
def list_tokens(
    agent_id: str, service: AgentTokenService = Depends(get_agent_token_service)
) -> list[AgentTokenResponse]:
    try:
        tokens = service.list_tokens(agent_id)
    except AgentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [AgentTokenResponse.from_domain(t) for t in tokens]


@router.delete("/{token_id}", response_model=AgentTokenResponse)
def revoke_token(
    agent_id: str, token_id: str, service: AgentTokenService = Depends(get_agent_token_service)
) -> AgentTokenResponse:
    try:
        token = service.revoke_token(agent_id, token_id)
    except AgentTokenNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AgentTokenResponse.from_domain(token)
