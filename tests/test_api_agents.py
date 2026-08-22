# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest
from fastapi.testclient import TestClient

import container
from api.main import app
from config import get_settings

API_KEY = get_settings().api_key
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(autouse=True)
def reset_container():
    """يعزل كل اختبار عبر مستودع/خدمة جديدة تمامًا (لا تسرب حالة بين الاختبارات)."""
    container.get_event_bus.cache_clear()
    container.get_agent_repository.cache_clear()
    container.get_agent_service.cache_clear()
    yield
    container.get_event_bus.cache_clear()
    container.get_agent_repository.cache_clear()
    container.get_agent_service.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_check(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_agent_requires_api_key(client: TestClient):
    resp = client.post("/agents", json={"name": "x", "permissions": [], "goals": []})
    assert resp.status_code == 401


def test_register_agent_rejects_wrong_api_key(client: TestClient):
    resp = client.post(
        "/agents", json={"name": "x", "permissions": [], "goals": []}, headers={"X-API-Key": "wrong"}
    )
    assert resp.status_code == 401


def test_register_and_fetch_agent(client: TestClient):
    resp = client.post(
        "/agents",
        json={"name": "scout-01", "permissions": ["read:memory"], "goals": ["watch"]},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "scout-01"
    agent_id = body["agent_id"]

    resp2 = client.get(f"/agents/{agent_id}", headers=HEADERS)
    assert resp2.status_code == 200
    assert resp2.json()["agent_id"] == agent_id


def test_register_agent_invalid_permission_returns_400(client: TestClient):
    resp = client.post(
        "/agents", json={"name": "bad", "permissions": ["sudo:root"], "goals": []}, headers=HEADERS
    )
    assert resp.status_code == 400


def test_get_unknown_agent_returns_404(client: TestClient):
    resp = client.get("/agents/unknown-id", headers=HEADERS)
    assert resp.status_code == 404


def test_state_transition_flow(client: TestClient):
    reg = client.post("/agents", json={"name": "a", "permissions": [], "goals": []}, headers=HEADERS)
    agent_id = reg.json()["agent_id"]

    ok = client.patch(f"/agents/{agent_id}/state", json={"target_state": "idle"}, headers=HEADERS)
    assert ok.status_code == 200
    assert ok.json()["state"] == "idle"

    bad = client.patch(f"/agents/{agent_id}/state", json={"target_state": "terminated"}, headers=HEADERS)
    assert bad.status_code == 200
    conflict = client.patch(f"/agents/{agent_id}/state", json={"target_state": "running"}, headers=HEADERS)
    assert conflict.status_code == 409


def test_metrics_endpoint(client: TestClient):
    resp = client.get("/metrics/system", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "cpu_percent" in body
    assert "ram_rss_mb" in body
