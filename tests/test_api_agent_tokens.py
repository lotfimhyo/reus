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


def _register_agent(client: TestClient, permissions: list[str] | None = None) -> str:
    resp = client.post(
        "/agents",
        json={"name": "token-agent", "permissions": permissions or ["read:memory", "write:memory"], "goals": []},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()["agent_id"]


def test_issue_token_requires_master_key(client: TestClient):
    agent_id = _register_agent(client)
    resp = client.post(f"/agents/{agent_id}/tokens", json={"label": "x"})
    assert resp.status_code == 401


def test_issue_token_for_unknown_agent_returns_404(client: TestClient):
    resp = client.post("/agents/ghost-agent/tokens", json={"label": "x"}, headers=HEADERS)
    assert resp.status_code == 404


def test_issue_and_list_tokens(client: TestClient):
    agent_id = _register_agent(client)
    issue = client.post(f"/agents/{agent_id}/tokens", json={"label": "worker-1"}, headers=HEADERS)
    assert issue.status_code == 201
    assert issue.json()["plaintext"].startswith("rvos_")

    listing = client.get(f"/agents/{agent_id}/tokens", headers=HEADERS)
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert "plaintext" not in listing.json()[0]  # لا يظهر النص الصافي في السرد أبدًا
    assert "token_hash" not in listing.json()[0]


def test_agent_token_can_access_its_own_memory(client: TestClient):
    agent_id = _register_agent(client)
    issue = client.post(f"/agents/{agent_id}/tokens", json={"label": "self"}, headers=HEADERS)
    agent_token = issue.json()["plaintext"]

    resp = client.post(
        f"/agents/{agent_id}/memory",
        json={"content": "خاطرة الوكيل الخاصة", "tags": []},
        headers={"X-API-Key": agent_token},
    )
    assert resp.status_code == 201


def test_agent_token_cannot_access_other_agents_memory(client: TestClient):
    agent_a = _register_agent(client)
    agent_b = _register_agent(client)
    issue = client.post(f"/agents/{agent_a}/tokens", json={"label": "self"}, headers=HEADERS)
    token_for_a = issue.json()["plaintext"]

    resp = client.post(
        f"/agents/{agent_b}/memory",
        json={"content": "محاولة انتحال شخصية", "tags": []},
        headers={"X-API-Key": token_for_a},
    )
    assert resp.status_code == 401


def test_revoked_token_loses_access(client: TestClient):
    agent_id = _register_agent(client)
    issue = client.post(f"/agents/{agent_id}/tokens", json={"label": "self"}, headers=HEADERS)
    token_id = issue.json()["token_id"]
    plaintext = issue.json()["plaintext"]

    revoke = client.delete(f"/agents/{agent_id}/tokens/{token_id}", headers=HEADERS)
    assert revoke.status_code == 200
    assert revoke.json()["revoked"] is True

    resp = client.get(f"/agents/{agent_id}/memory", headers={"X-API-Key": plaintext})
    assert resp.status_code == 401


def test_master_key_still_works_alongside_agent_tokens(client: TestClient):
    agent_id = _register_agent(client)
    resp = client.get(f"/agents/{agent_id}/memory", headers=HEADERS)
    assert resp.status_code == 200


def test_garbage_token_rejected(client: TestClient):
    agent_id = _register_agent(client)
    resp = client.get(f"/agents/{agent_id}/memory", headers={"X-API-Key": "rvos_not-a-real-token"})
    assert resp.status_code == 401


def test_revoke_unknown_token_returns_404(client: TestClient):
    agent_id = _register_agent(client)
    resp = client.delete(f"/agents/{agent_id}/tokens/ghost-token-id", headers=HEADERS)
    assert resp.status_code == 404


# ---------- Token Scopes ----------


def test_issue_token_with_scope_exceeding_agent_permissions_returns_400(client: TestClient):
    agent_id = _register_agent(client, permissions=["read:memory"])
    resp = client.post(
        f"/agents/{agent_id}/tokens",
        json={"label": "over-scoped", "scopes": ["read:memory", "write:memory"]},
        headers=HEADERS,
    )
    assert resp.status_code == 400


def test_read_only_scoped_token_can_search_but_not_store(client: TestClient):
    agent_id = _register_agent(client, permissions=["read:memory", "write:memory"])
    issue = client.post(
        f"/agents/{agent_id}/tokens", json={"label": "readonly", "scopes": ["read:memory"]}, headers=HEADERS
    )
    assert issue.json()["scopes"] == ["read:memory"]
    readonly_token = issue.json()["plaintext"]

    read_resp = client.get(f"/agents/{agent_id}/memory", headers={"X-API-Key": readonly_token})
    assert read_resp.status_code == 200

    write_resp = client.post(
        f"/agents/{agent_id}/memory",
        json={"content": "محاولة كتابة برمز قراءة فقط", "tags": []},
        headers={"X-API-Key": readonly_token},
    )
    assert write_resp.status_code == 403
    assert "نطاق" in write_resp.json()["detail"]


def test_write_only_scoped_token_can_store_but_not_search(client: TestClient):
    agent_id = _register_agent(client, permissions=["read:memory", "write:memory"])
    issue = client.post(
        f"/agents/{agent_id}/tokens", json={"label": "writeonly", "scopes": ["write:memory"]}, headers=HEADERS
    )
    writeonly_token = issue.json()["plaintext"]

    write_resp = client.post(
        f"/agents/{agent_id}/memory", json={"content": "يُخزَّن بنجاح", "tags": []}, headers={"X-API-Key": writeonly_token}
    )
    assert write_resp.status_code == 201

    search_resp = client.post(
        f"/agents/{agent_id}/memory/search", json={"query": "أي شيء"}, headers={"X-API-Key": writeonly_token}
    )
    assert search_resp.status_code == 403


def test_token_without_explicit_scopes_inherits_full_permissions(client: TestClient):
    agent_id = _register_agent(client, permissions=["read:memory", "write:memory"])
    issue = client.post(f"/agents/{agent_id}/tokens", json={"label": "full"}, headers=HEADERS)

    assert set(issue.json()["scopes"]) == {"read:memory", "write:memory"}

    token = issue.json()["plaintext"]
    write_resp = client.post(
        f"/agents/{agent_id}/memory", json={"content": "test", "tags": []}, headers={"X-API-Key": token}
    )
    assert write_resp.status_code == 201


def test_master_key_bypasses_scope_restrictions_entirely(client: TestClient):
    """المفتاح الرئيسي لا يتأثر بأي نطاق رمز؛ صلاحية إدارية كاملة دائمًا."""
    agent_id = _register_agent(client, permissions=["read:memory", "write:memory"])
    resp = client.post(
        f"/agents/{agent_id}/memory", json={"content": "عبر المفتاح الرئيسي", "tags": []}, headers=HEADERS
    )
    assert resp.status_code == 201
