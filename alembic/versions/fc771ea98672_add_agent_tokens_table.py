# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""add agent_tokens table

Revision ID: fc771ea98672
Revises: 00a99982a4e7
Create Date: 2026-07-09 00:18:42.186929

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc771ea98672'
down_revision: Union[str, Sequence[str], None] = '00a99982a4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_tokens",
        sa.Column("token_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("token_id"),
    )
    op.create_index(op.f("ix_agent_tokens_agent_id"), "agent_tokens", ["agent_id"], unique=False)
    op.create_index(op.f("ix_agent_tokens_token_hash"), "agent_tokens", ["token_hash"], unique=True)
    op.create_index(op.f("ix_agent_tokens_revoked"), "agent_tokens", ["revoked"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_agent_tokens_revoked"), table_name="agent_tokens")
    op.drop_index(op.f("ix_agent_tokens_token_hash"), table_name="agent_tokens")
    op.drop_index(op.f("ix_agent_tokens_agent_id"), table_name="agent_tokens")
    op.drop_table("agent_tokens")
