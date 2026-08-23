# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""encrypt memory content at rest

Replaces the memory_records.content column (plaintext) with
content_encrypted (bytea). Existing data is encrypted during this migration,
not merely converted to a different column type, using REUS_ENCRYPTION_KEY so
that no sensitive plaintext remains on disk.

Revision ID: 00a99982a4e7
Revises: c1dd83a102ca
Create Date: 2026-07-08 01:46:44.202989

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from config import get_settings
from infrastructure.encryption import EncryptionService

# revision identifiers, used by Alembic.
revision: str = '00a99982a4e7'
down_revision: Union[str, Sequence[str], None] = 'c1dd83a102ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_memory_records = sa.table(
    "memory_records",
    sa.column("memory_id", sa.String),
    sa.column("content", sa.Text),
    sa.column("content_encrypted", sa.LargeBinary),
)


def upgrade() -> None:
    """Upgrade schema."""
    encryption = EncryptionService(key=get_settings().encryption_key)  # Fails explicitly if the key is not configured.

    op.add_column("memory_records", sa.Column("content_encrypted", sa.LargeBinary(), nullable=True))

    connection = op.get_bind()
    existing_rows = connection.execute(sa.select(_memory_records.c.memory_id, _memory_records.c.content)).fetchall()
    for memory_id, content in existing_rows:
        connection.execute(
            _memory_records.update()
            .where(_memory_records.c.memory_id == memory_id)
            .values(content_encrypted=encryption.encrypt_text(content))
        )

    op.alter_column("memory_records", "content_encrypted", nullable=False)
    op.drop_column("memory_records", "content")


def downgrade() -> None:
    """Downgrade schema."""
    encryption = EncryptionService(key=get_settings().encryption_key)

    op.add_column("memory_records", sa.Column("content", sa.Text(), nullable=True))

    connection = op.get_bind()
    existing_rows = connection.execute(
        sa.select(_memory_records.c.memory_id, _memory_records.c.content_encrypted)
    ).fetchall()
    for memory_id, content_encrypted in existing_rows:
        connection.execute(
            _memory_records.update()
            .where(_memory_records.c.memory_id == memory_id)
            .values(content=encryption.decrypt_text(content_encrypted))
        )

    op.alter_column("memory_records", "content", nullable=False)
    op.drop_column("memory_records", "content_encrypted")
