"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Administrative observability and human-governed decisions for autonomy.
These routes are intentionally separate from the public chat surface and all
mutations retain the same admin API-key boundary as other control-plane APIs.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config import get_settings
from container import get_autonomy_governance_ledger, get_autonomy_supervisor, get_capability_layer
from infrastructure.security import verify_api_key


router = APIRouter(prefix="/autonomy", tags=["autonomy"], dependencies=[Depends(verify_api_key)])


class DecisionRequest(BaseModel):
    reviewer_note: str = Field(min_length=1, max_length=1_000)


def _proposal_payload(proposal) -> dict:
    return {
        "proposal_id": proposal.proposal_id,
        "goal_id": proposal.goal_id,
        "status": proposal.status.value,
        "rationale": proposal.rationale,
        "reviewer_note": proposal.reviewer_note,
        "capability": proposal.draft.spec.capability,
        "risk_level": proposal.draft.risk_level.value,
        "estimated_cost": proposal.draft.estimated_cost,
    }


def _ensure_enabled() -> None:
    if not get_settings().autonomy_enabled:
        raise HTTPException(status_code=409, detail="autonomy is disabled by policy")


@router.get("/status")
def status() -> dict:
    settings = get_settings()
    ledger = get_autonomy_governance_ledger()
    capabilities = get_capability_layer().discover()
    return {
        "enabled": settings.autonomy_enabled,
        "allow_agent_design": settings.autonomy_allow_agent_design,
        "auto_promote_low_risk": settings.autonomy_auto_promote_low_risk,
        "max_agent_builds_per_goal": settings.autonomy_max_agent_builds_per_goal,
        "registered_capabilities": len(capabilities),
        "proposal_counts": ledger.status_counts(),
    }


@router.get("/proposals")
def proposals() -> dict:
    ledger = get_autonomy_governance_ledger()
    return {"proposals": [_proposal_payload(proposal) for proposal in ledger.list_all()]}


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: str, decision: DecisionRequest) -> dict:
    _ensure_enabled()
    try:
        proposal = get_autonomy_supervisor().approve(proposal_id, reviewer_note=decision.reviewer_note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown autonomy proposal") from exc
    return _proposal_payload(proposal)


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: str, decision: DecisionRequest) -> dict:
    _ensure_enabled()
    try:
        proposal = get_autonomy_supervisor().reject(proposal_id, reviewer_note=decision.reviewer_note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown autonomy proposal") from exc
    return _proposal_payload(proposal)
