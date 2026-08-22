# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest
from fastapi.testclient import TestClient

import container
from api.main import app
from config import get_settings

HEADERS = {"X-API-Key": get_settings().api_key}

ALL_CACHES = (
    "get_event_bus",
    "get_agent_repository",
    "get_agent_service",
    "get_embedder",
    "get_memory_repository",
    "get_memory_service",
    "get_workflow_repository",
    "get_orchestrator_service",
    "get_agent_token_repository",
    "get_agent_token_service",
    "get_event_log_repository",
    "get_observability_service",
)


@pytest.fixture(autouse=True)
def reset_container():
    for name in ALL_CACHES:
        getattr(container, name).cache_clear()
    yield
    for name in ALL_CACHES:
        getattr(container, name).cache_clear()


def test_summary_and_events_via_running_app():
    """
    يستخدم `with client:` عمدًا لتشغيل lifespan فعليًا (وهو ما يبدأ تسجيل الأحداث)،
    بعكس بقية اختبارات API في هذا المشروع التي لا تحتاج ذلك.
    """
    with TestClient(app) as client:
        reg = client.post("/agents", json={"name": "obs-agent", "permissions": [], "goals": []}, headers=HEADERS)
        assert reg.status_code == 201

        summary = client.get("/observability/summary", headers=HEADERS)
        assert summary.status_code == 200
        # 2 لا 1: هذا الاختبار يُشغِّل lifespan الحقيقي عمدًا (with client:)،
        # فيتضمن الوكيل الافتراضي المبذور تلقائيًا عند الإقلاع
        # (infrastructure/seed_default_agent.py) بالإضافة إلى obs-agent
        # المسجَّل هنا صراحة.
        assert summary.json()["agents_total"] == 2

        events = client.get("/observability/events", headers=HEADERS)
        assert events.status_code == 200
        assert any(e["name"] == "agent.created" for e in events.json())


def test_observability_requires_api_key():
    with TestClient(app) as client:
        resp = client.get("/observability/summary")
        assert resp.status_code == 401


def test_events_filter_by_name_via_api():
    with TestClient(app) as client:
        client.post("/agents", json={"name": "a", "permissions": [], "goals": []}, headers=HEADERS)
        resp = client.get("/observability/events", params={"name": "agent.created"}, headers=HEADERS)
        assert resp.status_code == 200
        assert all(e["name"] == "agent.created" for e in resp.json())
