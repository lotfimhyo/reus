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
)


@pytest.fixture(autouse=True)
def reset_container():
    for name in ALL_CACHES:
        getattr(container, name).cache_clear()
    yield
    for name in ALL_CACHES:
        getattr(container, name).cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_create_linear_workflow(client: TestClient):
    resp = client.post(
        "/workflows",
        json={"name": "pipeline", "tasks": [{"name": "fetch"}, {"name": "process", "depends_on": ["fetch"]}]},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["tasks"]) == 2
    fetch_task = next(t for t in body["tasks"] if t["name"] == "fetch")
    assert fetch_task["state"] == "ready"


def test_cycle_returns_400(client: TestClient):
    resp = client.post(
        "/workflows",
        json={"name": "bad", "tasks": [{"name": "a", "depends_on": ["b"]}, {"name": "b", "depends_on": ["a"]}]},
        headers=HEADERS,
    )
    assert resp.status_code == 400


def test_unknown_agent_returns_404(client: TestClient):
    resp = client.post(
        "/workflows",
        json={"name": "wf", "tasks": [{"name": "t1", "agent_id": "ghost"}]},
        headers=HEADERS,
    )
    assert resp.status_code == 404


def test_full_lifecycle_via_api(client: TestClient):
    create = client.post("/workflows", json={"name": "wf", "tasks": [{"name": "only"}]}, headers=HEADERS)
    workflow_id = create.json()["workflow_id"]
    task_id = create.json()["tasks"][0]["task_id"]

    ready = client.get(f"/workflows/{workflow_id}/ready-tasks", headers=HEADERS)
    assert ready.status_code == 200
    assert len(ready.json()) == 1

    start = client.post(f"/workflows/{workflow_id}/tasks/{task_id}/start", headers=HEADERS)
    assert start.status_code == 200
    assert start.json()["state"] == "running"

    complete = client.post(
        f"/workflows/{workflow_id}/tasks/{task_id}/complete", json={"result": {"rows": 10}}, headers=HEADERS
    )
    assert complete.status_code == 200
    assert complete.json()["is_complete"] is True


def test_double_start_returns_409(client: TestClient):
    create = client.post("/workflows", json={"name": "wf", "tasks": [{"name": "only"}]}, headers=HEADERS)
    workflow_id = create.json()["workflow_id"]
    task_id = create.json()["tasks"][0]["task_id"]

    client.post(f"/workflows/{workflow_id}/tasks/{task_id}/start", headers=HEADERS)
    second = client.post(f"/workflows/{workflow_id}/tasks/{task_id}/start", headers=HEADERS)
    assert second.status_code == 409


def test_fail_permanently_cancels_dependents_via_api(client: TestClient):
    create = client.post(
        "/workflows",
        json={"name": "wf", "tasks": [{"name": "root"}, {"name": "child", "depends_on": ["root"]}]},
        headers=HEADERS,
    )
    workflow_id = create.json()["workflow_id"]
    root_id = next(t["task_id"] for t in create.json()["tasks"] if t["name"] == "root")

    client.post(f"/workflows/{workflow_id}/tasks/{root_id}/start", headers=HEADERS)
    fail_resp = client.post(f"/workflows/{workflow_id}/tasks/{root_id}/fail", json={"error": "boom"}, headers=HEADERS)

    assert fail_resp.status_code == 200
    body = fail_resp.json()
    assert body["has_permanent_failure"] is True
    child = next(t for t in body["tasks"] if t["name"] == "child")
    assert child["state"] == "cancelled"


def test_get_unknown_workflow_returns_404(client: TestClient):
    resp = client.get("/workflows/unknown-id", headers=HEADERS)
    assert resp.status_code == 404
