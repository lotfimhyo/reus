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


@pytest.fixture(autouse=True)
def reset_container():
    for fn in (
        container.get_event_bus,
        container.get_agent_repository,
        container.get_agent_service,
        container.get_embedder,
        container.get_memory_repository,
        container.get_memory_service,
    ):
        fn.cache_clear()
    yield
    for fn in (
        container.get_event_bus,
        container.get_agent_repository,
        container.get_agent_service,
        container.get_embedder,
        container.get_memory_repository,
        container.get_memory_service,
    ):
        fn.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _register_agent(client: TestClient, permissions: list[str]) -> str:
    resp = client.post(
        "/agents", json={"name": "mem-agent", "permissions": permissions, "goals": []}, headers=HEADERS
    )
    assert resp.status_code == 201
    return resp.json()["agent_id"]


def test_store_and_list_memory(client: TestClient):
    agent_id = _register_agent(client, ["read:memory", "write:memory"])

    resp = client.post(
        f"/agents/{agent_id}/memory", json={"content": "the sky is blue", "tags": ["fact"]}, headers=HEADERS
    )
    assert resp.status_code == 201
    memory_id = resp.json()["memory_id"]

    listing = client.get(f"/agents/{agent_id}/memory", headers=HEADERS)
    assert listing.status_code == 200
    assert any(m["memory_id"] == memory_id for m in listing.json())


def test_store_without_permission_returns_403(client: TestClient):
    agent_id = _register_agent(client, ["read:memory"])
    resp = client.post(f"/agents/{agent_id}/memory", json={"content": "x", "tags": []}, headers=HEADERS)
    assert resp.status_code == 403


def test_search_memory(client: TestClient):
    agent_id = _register_agent(client, ["read:memory", "write:memory"])
    client.post(
        f"/agents/{agent_id}/memory",
        json={"content": "quarterly revenue increased significantly", "tags": []},
        headers=HEADERS,
    )
    resp = client.post(
        f"/agents/{agent_id}/memory/search", json={"query": "revenue growth this quarter", "top_k": 3}, headers=HEADERS
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_forget_memory(client: TestClient):
    agent_id = _register_agent(client, ["read:memory", "write:memory"])
    store_resp = client.post(f"/agents/{agent_id}/memory", json={"content": "delete me", "tags": []}, headers=HEADERS)
    memory_id = store_resp.json()["memory_id"]

    delete_resp = client.delete(f"/agents/{agent_id}/memory/{memory_id}", headers=HEADERS)
    assert delete_resp.status_code == 204

    listing = client.get(f"/agents/{agent_id}/memory", headers=HEADERS)
    assert all(m["memory_id"] != memory_id for m in listing.json())


def test_memory_for_unknown_agent_returns_404(client: TestClient):
    resp = client.get("/agents/unknown-agent/memory", headers=HEADERS)
    assert resp.status_code == 404
