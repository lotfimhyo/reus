# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
PostgresAgentRepository: يلتزم بواجهة AgentRepository المجردة تمامًا،
لذا يمكن استبداله بـ InMemoryAgentRepository بتغيير سطر واحد في container.py
دون أي تعديل في application/ أو api/.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from domain.entities import Agent, AgentState, OperationRecord, PerformanceMetrics
from domain.repositories import AgentNotFound, AgentRepository
from infrastructure.postgres.models import AgentModel
from infrastructure.postgres.session import new_session


def _agent_to_row(agent: Agent) -> dict:
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "state": agent.state.value,
        "permissions": sorted(agent.permissions),
        "goals": agent.goals,
        "memory_refs": agent.memory_refs,
        "operation_log": [
            {
                "timestamp": op.timestamp.isoformat(),
                "action": op.action,
                "result": op.result,
                "metadata": op.metadata,
            }
            for op in agent.operation_log
        ],
        "metrics": {
            "requests_count": agent.metrics.requests_count,
            "total_latency_ms": agent.metrics.total_latency_ms,
            "errors_count": agent.metrics.errors_count,
            "last_cpu_percent": agent.metrics.last_cpu_percent,
            "last_rss_bytes": agent.metrics.last_rss_bytes,
        },
        "created_at": agent.created_at,
    }


def _row_to_agent(row: AgentModel) -> Agent:
    agent = Agent(
        name=row.name,
        permissions=set(row.permissions),
        goals=list(row.goals),
        agent_id=row.agent_id,
        state=AgentState(row.state),
        created_at=row.created_at,
    )
    agent.memory_refs = list(row.memory_refs)
    agent.operation_log = [
        OperationRecord(
            timestamp=datetime.fromisoformat(op["timestamp"]),
            action=op["action"],
            result=op["result"],
            metadata=op.get("metadata", {}),
        )
        for op in row.operation_log
    ]
    m = row.metrics
    agent.metrics = PerformanceMetrics(
        requests_count=m.get("requests_count", 0),
        total_latency_ms=m.get("total_latency_ms", 0.0),
        errors_count=m.get("errors_count", 0),
        last_cpu_percent=m.get("last_cpu_percent"),
        last_rss_bytes=m.get("last_rss_bytes"),
    )
    return agent


class PostgresAgentRepository(AgentRepository):
    def add(self, agent: Agent) -> None:
        with new_session() as session:  # type: Session
            session.add(AgentModel(**_agent_to_row(agent)))
            session.commit()

    def get(self, agent_id: str) -> Agent:
        with new_session() as session:
            row = session.get(AgentModel, agent_id)
            if row is None:
                raise AgentNotFound(agent_id)
            return _row_to_agent(row)

    def list_all(self) -> list[Agent]:
        with new_session() as session:
            rows = session.execute(select(AgentModel)).scalars().all()
            return [_row_to_agent(r) for r in rows]

    def update(self, agent: Agent) -> None:
        with new_session() as session:
            row = session.get(AgentModel, agent.agent_id)
            if row is None:
                raise AgentNotFound(agent.agent_id)
            for key, value in _agent_to_row(agent).items():
                setattr(row, key, value)
            session.commit()

    def delete(self, agent_id: str) -> None:
        with new_session() as session:
            row = session.get(AgentModel, agent_id)
            if row is None:
                raise AgentNotFound(agent_id)
            session.delete(row)
            session.commit()
