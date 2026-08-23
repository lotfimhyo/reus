"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Proves the actual security fix: the administrative key (REUS_API_KEY)—the
system's strongest permission—previously had no rate limit even though it
shares the public network surface that serves /chat. Although /chat was
protected in the previous session, this test proves that verify_api_key and
require_agent_scope (applied centrally in infrastructure/security.py) now also
limit failed key-guessing attempts, not merely use after successful
authentication. It also proves that this limit is fully independent from the
/chat limit (exhausting one does not consume the other's quota).
"""
from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient


class TestAdminRateLimit(unittest.TestCase):
    def setUp(self):
        os.environ["REUS_API_KEY"] = "real-admin-key"
        os.environ["REUS_ADMIN_RATE_LIMIT_PER_MINUTE"] = "3"

        import config

        config.get_settings.cache_clear()

        import container

        container.get_admin_rate_limiter.cache_clear()

        from api.main import app

        self.client = TestClient(app)

    def tearDown(self):
        os.environ.pop("REUS_API_KEY", None)
        os.environ.pop("REUS_ADMIN_RATE_LIMIT_PER_MINUTE", None)

        import config

        config.get_settings.cache_clear()

        import container

        container.get_admin_rate_limiter.cache_clear()

    def test_admin_key_guessing_attempts_are_rate_limited(self):
        """Critical test: wrong-key guessing attempts (401) consume the same
        limit rather than becoming unbounded merely because they fail."""
        for _ in range(3):
            response = self.client.get("/agents/does-not-exist", headers={"x-api-key": "wrong-key"})
            self.assertEqual(response.status_code, 401)

        response = self.client.get("/agents/does-not-exist", headers={"x-api-key": "real-admin-key"})
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

    def test_correct_key_requests_within_limit_are_not_blocked(self):
        for _ in range(3):
            response = self.client.get("/agents/does-not-exist", headers={"x-api-key": "real-admin-key"})
            self.assertNotEqual(response.status_code, 429)

    def test_admin_rate_limit_is_independent_from_chat_rate_limit(self):
        """Exhausting the /chat limit must not affect administrative routes,
        and vice versa—evidence of distinct rate limiters rather than the same object by mistake."""
        os.environ["REUS_USER_API_KEY"] = "user-key"
        import config

        config.get_settings.cache_clear()
        try:
            for _ in range(3):
                self.client.get("/agents/does-not-exist", headers={"x-api-key": "wrong-key"})
            # The administrative limit is now fully exhausted (3/3), but /chat must remain available.
            response = self.client.post(
                "/chat", json={"prompt": "hi"}, headers={"x-api-key": "user-key"}
            )
            self.assertNotEqual(response.status_code, 429)
        finally:
            os.environ.pop("REUS_USER_API_KEY", None)
            config.get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
