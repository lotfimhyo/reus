"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Proves that /health remains an inexpensive liveness probe that checks no
dependency, while /ready actually checks enabled dependencies (readiness) and
returns an explicit 503 when any is unreachable rather than falsely declaring
the service ready.
"""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.main import app


class TestHealthAndReady(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_is_always_ok_and_cheap(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_ready_reports_ok_when_backends_are_memory(self):
        """The default test environment uses storage_backend=memory and
        event_bus_backend=memory. No external dependency needs checking, so it
        must declare readiness immediately while explaining that checks were
        skipped rather than pretending they succeeded."""
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        self.assertIn("skipped", body["checks"]["database"])
        self.assertIn("skipped", body["checks"]["redis"])

    def test_ready_returns_503_when_configured_postgres_is_unreachable(self):
        """This test intentionally changes REUS_DATABASE_URL in-process, which
        does not happen in production (it is set once at startup). It exposed
        that get_engine()/get_session_factory() in infrastructure/postgres/
        session.py are cached with @lru_cache independently of get_settings().
        Unless explicitly cleared here, a broken database engine remains cached
        for the process lifetime and corrupts later real PostgreSQL tests in
        the same session. This was discovered through execution, not theory:
        this exact test caused 19 tests in tests/test_postgres_repositories.py
        to fail when the full suite ran, even though each passed alone."""
        import os

        import config
        from config import Settings
        from infrastructure.postgres import session as postgres_session

        broken_settings = Settings(
            storage_backend="postgres",
            database_url="postgresql+psycopg://nouser:nopass@localhost:1/nonexistent_db_for_test",
        )
        app.dependency_overrides.clear()

        try:
            os.environ["REUS_STORAGE_BACKEND"] = "postgres"
            os.environ["REUS_DATABASE_URL"] = broken_settings.database_url
            config.get_settings.cache_clear()
            postgres_session.get_engine.cache_clear()
            postgres_session.get_session_factory.cache_clear()

            response = self.client.get("/ready")
            self.assertEqual(response.status_code, 503)
            body = response.json()["detail"]
            self.assertEqual(body["status"], "not_ready")
            self.assertIn("unreachable", body["checks"]["database"])
        finally:
            os.environ.pop("REUS_STORAGE_BACKEND", None)
            os.environ.pop("REUS_DATABASE_URL", None)
            config.get_settings.cache_clear()
            # Critical: without this, the broken engine above remains cached
            # for the rest of the session despite resetting settings; see above.
            postgres_session.get_engine.cache_clear()
            postgres_session.get_session_factory.cache_clear()


if __name__ == "__main__":
    unittest.main()
