"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.autonomy import router
from infrastructure.security import verify_api_key


def test_status_is_available_to_admin_surface_with_autonomy_disabled(monkeypatch):
    class Settings:
        autonomy_enabled = False
        autonomy_allow_agent_design = True
        autonomy_auto_promote_low_risk = False
        autonomy_max_agent_builds_per_goal = 1

    monkeypatch.setattr("api.routes.autonomy.get_settings", lambda: Settings())
    monkeypatch.setattr("container.get_capability_layer", lambda: type("Layer", (), {"discover": lambda self: []})())
    monkeypatch.setattr("container.get_autonomy_governance_ledger", lambda: type("Ledger", (), {"status_counts": lambda self: {}})())

    app = FastAPI()
    app.dependency_overrides[verify_api_key] = lambda: None
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/autonomy/status")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
