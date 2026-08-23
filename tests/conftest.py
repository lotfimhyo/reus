"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Shared pytest configuration for every test file.

``get_admin_rate_limiter()`` and ``get_chat_rate_limiter()`` (container.py)
are deliberately cached at process scope with ``lru_cache``; that is correct
in production. However, it means test files that invoke protected routes with
TestClient share the same rate limiter throughout a pytest run and are counted
as the same client, causing the counter to accumulate across unrelated files.

This was observed directly: 29 tests returned 429 during the full suite while
passing alone. The correct fix is to clear limiter state between tests, not to
raise or disable the limit.
"""
import os

import pytest

# Tests must not depend on a local .env file or user secrets. These low-privilege
# synthetic values are set before importing units that call get_settings().
os.environ.setdefault("REUS_API_KEY", "test-admin-secret-12345678901234567890")
os.environ.setdefault("REUS_USER_API_KEY", "test-user-secret-12345678901234567890")
os.environ.setdefault("REUS_ENVIRONMENT", "test")
_TEST_ENVIRONMENT = {
    "REUS_API_KEY": "test-admin-secret-12345678901234567890",
    "REUS_USER_API_KEY": "test-user-secret-12345678901234567890",
    "REUS_ENVIRONMENT": "test",
}


@pytest.fixture(autouse=True)
def _isolate_settings_environment():
    import config

    previous = {key: os.environ.get(key) for key in _TEST_ENVIRONMENT}
    os.environ.update(_TEST_ENVIRONMENT)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    import container

    container.get_admin_rate_limiter.cache_clear()
    container.get_chat_rate_limiter.cache_clear()
    yield
    container.get_admin_rate_limiter.cache_clear()
    container.get_chat_rate_limiter.cache_clear()
