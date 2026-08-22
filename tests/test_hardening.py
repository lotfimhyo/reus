# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""اختبارات الحواجز الأمنية المضافة في مرحلة التحصين.

**المطور:** lotfi Mahiddine
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.main import app
from config import Settings
from infrastructure.rate_limiter import InMemoryRateLimiter


def test_production_rejects_placeholder_credentials():
    with pytest.raises(ValueError, match="REUS_API_KEY"):
        Settings(environment="production", api_key="change-me-in-production", user_api_key="valid-user-secret-123456789")


def test_production_accepts_unique_credentials_for_memory_backend():
    settings = Settings(
        environment="production",
        api_key="admin-secret-12345678901234567890",
        user_api_key="user-secret-12345678901234567890",
        storage_backend="memory",
        event_bus_backend="memory",
    )
    assert settings.environment == "production"


def test_rate_limiter_evicts_expired_keys_and_respects_capacity():
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=0.01, max_keys=2, cleanup_interval_seconds=0.001)
    assert limiter.allow("a")[0]
    assert limiter.allow("b")[0]
    time.sleep(0.02)
    assert limiter.allow("c")[0]
    assert len(limiter._hits) <= 2


def test_common_security_headers_are_present():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
