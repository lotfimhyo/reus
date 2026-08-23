# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""add scopes column to agent_tokens

Revision ID: 942779d14f7c
Revises: fc771ea98672
Create Date: 2026-07-11 19:27:13.710386

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '942779d14f7c'
down_revision: Union[str, Sequence[str], None] = 'fc771ea98672'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: add the column as nullable first so it can be populated for
    # every pre-existing row.
    op.add_column("agent_tokens", sa.Column("scopes", sa.JSON(), nullable=True))

    # Step 2: perform a real data migration. Every token issued before this
    # migration implicitly inherited its agent's permissions (the behavior
    # before scopes existed), so populate scopes with the agent's current
    # permissions instead of leaving it empty. Under the new semantics, empty
    # means "no permissions at all", which would abruptly remove permissions
    # from every existing token.
    op.execute(
        """
        UPDATE agent_tokens
        SET scopes = agents.permissions
        FROM agents
        WHERE agent_tokens.agent_id = agents.agent_id
        """
    )
    # Tokens whose agent was deleted later have no matching JOIN row above, so
    # explicitly populate them with an empty array.
    op.execute("UPDATE agent_tokens SET scopes = '[]'::json WHERE scopes IS NULL")

    # Step 3: after population is complete, enforce NOT NULL as required by
    # the column's final design.
    op.alter_column("agent_tokens", "scopes", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("agent_tokens", "scopes")
