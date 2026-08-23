# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Run: python3 -m infrastructure.postgres.init_db
Creates all tables (agents, memory_records, workflows) if they do not exist.

Important: this script is only suitable for quick local experimentation (it
creates tables in one step from the current model state). **Alembic is the
approved approach for managing real schema evolution** (see `alembic/`),
because it alone supports safe upgrades, downgrades, and a complete change
history. Do not use this script in an Alembic-managed production environment:
`create_all` does not record a revision in `alembic_version` and would later
cause a conflict.
"""
from __future__ import annotations

# Import all models before create_all so they are registered in Base.metadata.
from infrastructure.postgres.models import AgentModel, MemoryRecordModel, WorkflowModel  # noqa: F401
from infrastructure.postgres.session import Base, get_engine


def init_db() -> None:
    Base.metadata.create_all(get_engine())
    print("All tables were created or verified successfully. (Reminder: use Alembic in production.)")


if __name__ == "__main__":
    init_db()
