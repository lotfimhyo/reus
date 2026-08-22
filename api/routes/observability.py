# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.schemas_observability import EventLogEntryResponse, ObservabilitySummaryResponse
from application.observability_service import ObservabilityService
from container import get_observability_service
from infrastructure.security import verify_api_key

router = APIRouter(prefix="/observability", tags=["observability"], dependencies=[Depends(verify_api_key)])


@router.get("/summary", response_model=ObservabilitySummaryResponse)
def get_summary(
    recent_events_limit: int = Query(default=20, ge=1, le=200),
    service: ObservabilityService = Depends(get_observability_service),
) -> ObservabilitySummaryResponse:
    summary = service.get_summary(recent_events_limit=recent_events_limit)
    return ObservabilitySummaryResponse.from_domain(summary)


@router.get("/events", response_model=list[EventLogEntryResponse])
def get_events(
    limit: int = Query(default=100, ge=1, le=1000),
    name: str | None = None,
    service: ObservabilityService = Depends(get_observability_service),
) -> list[EventLogEntryResponse]:
    events = service.get_recent_events(limit=limit, name_filter=name)
    return [EventLogEntryResponse.from_domain(e) for e in events]
