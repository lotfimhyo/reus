# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
اختبارات تكامل على PostgreSQL فعلي (لا Mock). تتطلب خادم Postgres يعمل محليًا
(كما هو مُهيَّأ في هذه البيئة) بامتداد pgvector مُفعَّلًا. كل اختبار ينظّف بياناته بنفسه
حتى لا تتراكم صفوف بين التشغيلات.
"""
from __future__ import annotations

import pytest
from sqlalchemy import delete

from domain.agent_token import AgentToken
from domain.agent_token_repository import AgentTokenNotFound
from domain.entities import Agent, AgentState
from domain.memory import MemoryRecord
from domain.memory_repository import MemoryNotFound
from domain.repositories import AgentNotFound
from domain.workflow import TaskSpec, Workflow
from domain.workflow_repository import WorkflowNotFound
from infrastructure.encryption import EncryptionService
from infrastructure.postgres.agent_repository import PostgresAgentRepository
from infrastructure.postgres.agent_token_repository import PostgresAgentTokenRepository
from infrastructure.postgres.memory_repository import PostgresMemoryRepository
from infrastructure.postgres.models import AgentModel, AgentTokenModel, MemoryRecordModel, WorkflowModel
from infrastructure.postgres.session import new_session
from infrastructure.postgres.workflow_repository import PostgresWorkflowRepository

_TEST_ENCRYPTION = EncryptionService(key="7Z0nkRok2TiMlSgI0J76GObYendk0aPC9r8C4B8dzKo=")


def _memory_repo() -> PostgresMemoryRepository:
    return PostgresMemoryRepository(encryption=_TEST_ENCRYPTION)


@pytest.fixture(autouse=True)
def clean_tables():
    """يفرغ الجداول قبل كل اختبار وبعده لضمان عزل تام."""
    with new_session() as session:
        session.execute(delete(AgentTokenModel))
        session.execute(delete(MemoryRecordModel))
        session.execute(delete(WorkflowModel))
        session.execute(delete(AgentModel))
        session.commit()
    yield
    with new_session() as session:
        session.execute(delete(AgentTokenModel))
        session.execute(delete(MemoryRecordModel))
        session.execute(delete(WorkflowModel))
        session.execute(delete(AgentModel))
        session.commit()


# ---------- Agent ----------

def test_agent_add_and_get_roundtrip():
    repo = PostgresAgentRepository()
    agent = Agent(name="pg-agent", permissions={"read:memory"}, goals=["g1"])
    agent.record_operation(action="register", result="success")
    repo.add(agent)

    fetched = repo.get(agent.agent_id)
    assert fetched.name == "pg-agent"
    assert fetched.permissions == {"read:memory"}
    assert len(fetched.operation_log) == 1
    assert fetched.operation_log[0].action == "register"


def test_agent_get_missing_raises():
    repo = PostgresAgentRepository()
    with pytest.raises(AgentNotFound):
        repo.get("does-not-exist")


def test_agent_update_persists_state_and_metrics():
    repo = PostgresAgentRepository()
    agent = Agent(name="worker", permissions=set(), goals=[])
    repo.add(agent)

    agent.transition_to(AgentState.IDLE)
    agent.record_request(latency_ms=12.5, success=True)
    repo.update(agent)

    fetched = repo.get(agent.agent_id)
    assert fetched.state == AgentState.IDLE
    assert fetched.metrics.requests_count == 1
    assert fetched.metrics.avg_latency_ms == pytest.approx(12.5)


def test_agent_list_all_and_delete():
    repo = PostgresAgentRepository()
    a1 = Agent(name="a1", permissions=set(), goals=[])
    a2 = Agent(name="a2", permissions=set(), goals=[])
    repo.add(a1)
    repo.add(a2)
    assert len(repo.list_all()) == 2

    repo.delete(a1.agent_id)
    remaining = repo.list_all()
    assert len(remaining) == 1
    assert remaining[0].agent_id == a2.agent_id


# ---------- Memory (pgvector) ----------

def test_memory_add_get_and_soft_delete():
    repo = _memory_repo()
    record = MemoryRecord(agent_id="a1", content="hello from postgres")
    repo.add(record, embedding=[0.1] * 384)

    fetched = repo.get(record.memory_id)
    assert fetched.content == "hello from postgres"

    repo.delete(record.memory_id)
    with pytest.raises(MemoryNotFound):
        repo.get(record.memory_id)


def test_memory_search_orders_by_cosine_similarity():
    repo = _memory_repo()
    close = MemoryRecord(agent_id="a1", content="close vector")
    far = MemoryRecord(agent_id="a1", content="far vector")
    repo.add(close, embedding=[1.0] + [0.0] * 383)
    repo.add(far, embedding=[0.0, 1.0] + [0.0] * 382)

    results = repo.search(query_embedding=[1.0] + [0.0] * 383, top_k=2)
    assert results[0].record.memory_id == close.memory_id
    assert results[0].score > results[1].score


def test_memory_search_filters_by_agent():
    repo = _memory_repo()
    r1 = MemoryRecord(agent_id="agent-1", content="shared")
    r2 = MemoryRecord(agent_id="agent-2", content="shared")
    repo.add(r1, embedding=[1.0] + [0.0] * 383)
    repo.add(r2, embedding=[1.0] + [0.0] * 383)

    results = repo.search(query_embedding=[1.0] + [0.0] * 383, top_k=5, agent_id="agent-1")
    assert len(results) == 1
    assert results[0].record.agent_id == "agent-1"


def test_memory_list_by_agent_excludes_deleted():
    repo = _memory_repo()
    r1 = MemoryRecord(agent_id="a1", content="one")
    r2 = MemoryRecord(agent_id="a1", content="two")
    repo.add(r1, embedding=[0.1] * 384)
    repo.add(r2, embedding=[0.2] * 384)
    repo.delete(r2.memory_id)

    remaining = repo.list_by_agent("a1")
    assert len(remaining) == 1


def test_memory_content_is_actually_encrypted_on_disk():
    """
    الاختبار الحاسم لـ Encryption at Rest: يتحقق من العمود الخام في قاعدة البيانات
    مباشرة (وليس عبر PostgresMemoryRepository التي تفك التشفير تلقائيًا)، للتأكد
    أن النص الحساس لا يُخزَّن صافيًا على القرص بأي شكل من الأشكال.
    """
    repo = _memory_repo()
    secret_plaintext = "رقم البطاقة السري: 4111-1111-1111-1111"
    record = MemoryRecord(agent_id="a1", content=secret_plaintext)
    repo.add(record, embedding=[0.1] * 384)

    with new_session() as session:
        raw_row = session.get(MemoryRecordModel, record.memory_id)
        raw_bytes = raw_row.content_encrypted

    assert secret_plaintext.encode("utf-8") not in raw_bytes
    assert b"4111" not in raw_bytes
    # يبقى قابلًا لفك التشفير الصحيح عبر المستودع (الذي يملك EncryptionService)
    assert repo.get(record.memory_id).content == secret_plaintext


# ---------- Agent Tokens ----------

def test_token_add_and_get_by_hash():
    repo = PostgresAgentTokenRepository()
    token = AgentToken(agent_id="a1", token_hash="hash-abc", label="ci", scopes=frozenset({"read:memory"}))
    repo.add(token)

    fetched = repo.get_by_hash("hash-abc")
    assert fetched is not None
    assert fetched.agent_id == "a1"
    assert fetched.label == "ci"
    assert fetched.scopes == frozenset({"read:memory"})


def test_token_scopes_persist_as_empty_set_by_default():
    repo = PostgresAgentTokenRepository()
    token = AgentToken(agent_id="a1", token_hash="hash-empty-scopes")
    repo.add(token)

    fetched = repo.get_by_hash("hash-empty-scopes")
    assert fetched.scopes == frozenset()


def test_token_get_by_unknown_hash_returns_none():
    repo = PostgresAgentTokenRepository()
    assert repo.get_by_hash("does-not-exist") is None


def test_token_list_by_agent():
    repo = PostgresAgentTokenRepository()
    repo.add(AgentToken(agent_id="a1", token_hash="h1"))
    repo.add(AgentToken(agent_id="a1", token_hash="h2"))
    repo.add(AgentToken(agent_id="a2", token_hash="h3"))

    tokens = repo.list_by_agent("a1")
    assert len(tokens) == 2


def test_token_update_persists_revocation_and_last_used():
    repo = PostgresAgentTokenRepository()
    token = AgentToken(agent_id="a1", token_hash="h1")
    repo.add(token)

    token.mark_used()
    token.revoke()
    repo.update(token)

    fetched = repo.get_by_hash("h1")
    assert fetched.revoked is True
    assert fetched.last_used_at is not None


def test_token_update_missing_raises():
    repo = PostgresAgentTokenRepository()
    ghost = AgentToken(agent_id="a1", token_hash="h1", token_id="does-not-exist")
    with pytest.raises(AgentTokenNotFound):
        repo.update(ghost)


# ---------- Workflow ----------

def test_workflow_add_and_get_preserves_dag_structure():
    repo = PostgresWorkflowRepository()
    workflow = Workflow.create("wf", [TaskSpec(name="a"), TaskSpec(name="b", depends_on=["a"])])
    repo.add(workflow)

    fetched = repo.get(workflow.workflow_id)
    assert len(fetched.tasks) == 2
    b = next(t for t in fetched.tasks.values() if t.name == "b")
    a = next(t for t in fetched.tasks.values() if t.name == "a")
    assert a.task_id in b.depends_on


def test_workflow_get_missing_raises():
    repo = PostgresWorkflowRepository()
    with pytest.raises(WorkflowNotFound):
        repo.get("ghost-workflow")


def test_workflow_update_persists_task_state_changes():
    repo = PostgresWorkflowRepository()
    workflow = Workflow.create("wf", [TaskSpec(name="only")])
    repo.add(workflow)

    task_id = list(workflow.tasks.keys())[0]
    workflow.mark_ready(task_id)
    workflow.start_task(task_id)
    workflow.complete_task(task_id, result={"ok": True})
    repo.update(workflow)

    fetched = repo.get(workflow.workflow_id)
    assert fetched.is_complete() is True
    assert fetched.tasks[task_id].result == {"ok": True}


def test_workflow_list_all():
    repo = PostgresWorkflowRepository()
    repo.add(Workflow.create("wf1", [TaskSpec(name="a")]))
    repo.add(Workflow.create("wf2", [TaskSpec(name="a")]))
    assert len(repo.list_all()) == 2
