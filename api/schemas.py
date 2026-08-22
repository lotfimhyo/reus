# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from domain.entities import Agent, AgentState
from domain.memory import MemoryRecord
from domain.memory_repository import SearchResult


class RegisterAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    permissions: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)


class StateChangeRequest(BaseModel):
    target_state: AgentState


class PerformanceMetricsResponse(BaseModel):
    requests_count: int
    avg_latency_ms: float
    errors_count: int
    last_cpu_percent: float | None
    last_rss_bytes: int | None


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    state: AgentState
    permissions: list[str]
    goals: list[str]
    memory_refs: list[str]
    created_at: datetime
    metrics: PerformanceMetricsResponse

    @classmethod
    def from_domain(cls, agent: Agent) -> "AgentResponse":
        return cls(
            agent_id=agent.agent_id,
            name=agent.name,
            state=agent.state,
            permissions=sorted(agent.permissions),
            goals=agent.goals,
            memory_refs=agent.memory_refs,
            created_at=agent.created_at,
            metrics=PerformanceMetricsResponse(
                requests_count=agent.metrics.requests_count,
                avg_latency_ms=agent.metrics.avg_latency_ms,
                errors_count=agent.metrics.errors_count,
                last_cpu_percent=agent.metrics.last_cpu_percent,
                last_rss_bytes=agent.metrics.last_rss_bytes,
            ),
        )


class StoreMemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
    tags: list[str] = Field(default_factory=list)


class SearchMemoryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=50)


class MemoryRecordResponse(BaseModel):
    memory_id: str
    agent_id: str
    content: str
    tags: list[str]
    created_at: datetime

    @classmethod
    def from_domain(cls, record: MemoryRecord) -> "MemoryRecordResponse":
        return cls(
            memory_id=record.memory_id,
            agent_id=record.agent_id,
            content=record.content,
            tags=record.tags,
            created_at=record.created_at,
        )


class MemorySearchResultResponse(BaseModel):
    memory: MemoryRecordResponse
    score: float

    @classmethod
    def from_domain(cls, result: SearchResult) -> "MemorySearchResultResponse":
        return cls(memory=MemoryRecordResponse.from_domain(result.record), score=result.score)
