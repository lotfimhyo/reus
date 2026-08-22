# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
اختبار تكامل حقيقي لملف الـ migration الأولي. ينشئ قاعدة بيانات PostgreSQL فارغة
تمامًا (منفصلة عن قاعدة بيانات التطوير)، يطبّق upgrade → downgrade → upgrade عبر
واجهة Alembic البرمجية الفعلية، ويتحقق من وجود/غياب الجداول عبر SQLAlchemy Inspector
في كل مرحلة — وليس افتراضًا أن الأوامر "نجحت لأنها لم تُرفع استثناءً".

ملاحظة بيئة: إنشاء/حذف قاعدة البيانات وتفعيل امتداد pgvector يتطلبان صلاحيات
Superuser (كما هو الحال في أي بيئة PostgreSQL حقيقية)، لذا يُنفَّذان هنا عبر
مستخدم postgres، تمامًا كخطوة يقوم بها مسؤول قاعدة بيانات مرة واحدة قبل نشر
التطبيق. تطبيق الـ migration نفسه يتم عبر مستخدم التطبيق العادي (reus_veritas)
كما سيحدث فعليًا في الإنتاج.
"""
from __future__ import annotations

import os
import subprocess

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from config import get_settings

TEST_DB_NAME = "reus_veritas_migration_test_db"
TEST_DB_URL = f"postgresql+psycopg://reus_veritas:reus_veritas_dev_pw@localhost:5432/{TEST_DB_NAME}"


def _run_as_postgres(sql: str) -> None:
    subprocess.run(["su", "postgres", "-c", f"psql -v ON_ERROR_STOP=1 -c \"{sql}\""], check=True, capture_output=True)


def _run_as_postgres_on_db(db: str, sql: str) -> None:
    subprocess.run(
        ["su", "postgres", "-c", f'psql -v ON_ERROR_STOP=1 -d {db} -c "{sql}"'], check=True, capture_output=True
    )


@pytest.fixture
def fresh_database():
    """
    ينشئ قاعدة بيانات فارغة تمامًا، ويضبط REUS_DATABASE_URL الفعلي لتوجيه إليها.
    هذا ضروري لأن alembic/env.py يتجاوز عمدًا أي sqlalchemy.url يُمرَّر برمجيًا
    ويعتمد حصرًا على get_settings().database_url (مصدر الحقيقة الوحيد في المشروع)،
    لذا يجب محاكاة ذلك عبر متغير البيئة الفعلي وليس عبر Config فقط.
    """
    _run_as_postgres(f"DROP DATABASE IF EXISTS {TEST_DB_NAME};")
    _run_as_postgres(f"CREATE DATABASE {TEST_DB_NAME} OWNER reus_veritas;")
    _run_as_postgres_on_db(TEST_DB_NAME, "GRANT ALL ON SCHEMA public TO reus_veritas;")
    _run_as_postgres_on_db(TEST_DB_NAME, "CREATE EXTENSION IF NOT EXISTS vector;")

    original_url = os.environ.get("REUS_DATABASE_URL")
    os.environ["REUS_DATABASE_URL"] = TEST_DB_URL
    get_settings.cache_clear()

    yield TEST_DB_URL

    if original_url is None:
        os.environ.pop("REUS_DATABASE_URL", None)
    else:
        os.environ["REUS_DATABASE_URL"] = original_url
    get_settings.cache_clear()
    _run_as_postgres(f"DROP DATABASE IF EXISTS {TEST_DB_NAME};")


def _alembic_config(database_url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_creates_all_expected_tables(fresh_database):
    command.upgrade(_alembic_config(fresh_database), "head")

    tables = _table_names(fresh_database)
    assert {"agents", "memory_records", "workflows", "agent_tokens"}.issubset(tables)


def test_downgrade_removes_all_application_tables(fresh_database):
    cfg = _alembic_config(fresh_database)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, "base")

    tables = _table_names(fresh_database)
    assert "agents" not in tables
    assert "memory_records" not in tables
    assert "workflows" not in tables
    assert "agent_tokens" not in tables


def test_upgrade_is_reversible_round_trip(fresh_database):
    cfg = _alembic_config(fresh_database)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    tables = _table_names(fresh_database)
    assert {"agents", "memory_records", "workflows", "agent_tokens"}.issubset(tables)


def test_memory_records_embedding_column_uses_pgvector(fresh_database):
    command.upgrade(_alembic_config(fresh_database), "head")

    engine = create_engine(fresh_database)
    try:
        columns = {c["name"]: c["type"] for c in inspect(engine).get_columns("memory_records")}
    finally:
        engine.dispose()

    assert "embedding" in columns
    assert "VECTOR" in str(columns["embedding"]).upper()


def test_scopes_backfill_migration_inherits_agent_permissions_for_pre_existing_tokens(fresh_database):
    """
    يتحقق أن ترحيل إضافة عمود scopes (942779d14f7c) لا يترك رموزًا موجودة مسبقًا
    بمصفوفة فارغة (والتي تعني "بلا صلاحيات إطلاقًا" في المعنى الجديد) — بل يُعبّئها
    فعليًا بصلاحيات وكيلها الحالية وقت الترحيل، حتى لا تُسقَط فجأة رموز كانت تعمل.
    """
    from sqlalchemy import text

    cfg = _alembic_config(fresh_database)
    # التوقف عند الترحيل الذي يسبق إضافة scopes مباشرة، لإدراج بيانات "قديمة" واقعية
    command.upgrade(cfg, "fc771ea98672")

    engine = create_engine(fresh_database)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO agents (agent_id, name, state, permissions, goals, memory_refs, "
                    "operation_log, metrics, created_at) VALUES "
                    "('agent-1', 'legacy-agent', 'idle', '[\"read:memory\", \"write:memory\"]', "
                    "'[]', '[]', '[]', '{}', now())"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO agent_tokens (token_id, agent_id, token_hash, label, revoked, created_at) "
                    "VALUES ('token-1', 'agent-1', 'legacy-hash', 'legacy-token', false, now())"
                )
            )

        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            row = conn.execute(text("SELECT scopes FROM agent_tokens WHERE token_id = 'token-1'")).one()
    finally:
        engine.dispose()

    assert set(row.scopes) == {"read:memory", "write:memory"}
