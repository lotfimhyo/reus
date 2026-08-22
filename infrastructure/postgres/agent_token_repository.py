# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from sqlalchemy import select

from domain.agent_token import AgentToken
from domain.agent_token_repository import AgentTokenNotFound, AgentTokenRepository
from infrastructure.postgres.models import AgentTokenModel
from infrastructure.postgres.session import new_session


def _row_to_token(row: AgentTokenModel) -> AgentToken:
    return AgentToken(
        agent_id=row.agent_id,
        token_hash=row.token_hash,
        label=row.label,
        scopes=frozenset(row.scopes),
        token_id=row.token_id,
        revoked=row.revoked,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


class PostgresAgentTokenRepository(AgentTokenRepository):
    def add(self, token: AgentToken) -> None:
        with new_session() as session:
            session.add(
                AgentTokenModel(
                    token_id=token.token_id,
                    agent_id=token.agent_id,
                    token_hash=token.token_hash,
                    label=token.label,
                    scopes=sorted(token.scopes),
                    revoked=token.revoked,
                    created_at=token.created_at,
                    last_used_at=token.last_used_at,
                )
            )
            session.commit()

    def get_by_hash(self, token_hash: str) -> AgentToken | None:
        with new_session() as session:
            row = session.execute(
                select(AgentTokenModel).where(AgentTokenModel.token_hash == token_hash)
            ).scalar_one_or_none()
            return None if row is None else _row_to_token(row)

    def list_by_agent(self, agent_id: str) -> list[AgentToken]:
        with new_session() as session:
            rows = session.execute(
                select(AgentTokenModel).where(AgentTokenModel.agent_id == agent_id)
            ).scalars().all()
            return [_row_to_token(r) for r in rows]

    def update(self, token: AgentToken) -> None:
        with new_session() as session:
            row = session.get(AgentTokenModel, token.token_id)
            if row is None:
                raise AgentTokenNotFound(token.token_id)
            row.revoked = token.revoked
            row.last_used_at = token.last_used_at
            session.commit()
