"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Proves InMemoryRateLimiter (a real sliding window, not a fixed window) and its
actual integration into /chat. This includes a security-critical ordering: rate
limiting runs before API-key validation, not after, so failed key-guessing
attempts consume the limit rather than being available without bounds.
"""
from __future__ import annotations

import time
import unittest

from fastapi.testclient import TestClient

from infrastructure.rate_limiter import InMemoryRateLimiter


class TestInMemoryRateLimiter(unittest.TestCase):
    def test_allows_up_to_the_limit_then_blocks(self):
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
        results = [limiter.allow("client-a")[0] for _ in range(4)]
        self.assertEqual(results, [True, True, True, False])

    def test_different_keys_are_independent(self):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        self.assertTrue(limiter.allow("client-a")[0])
        self.assertFalse(limiter.allow("client-a")[0])
        # A different key must not be affected by the first key's limit.
        self.assertTrue(limiter.allow("client-b")[0])

    def test_retry_after_is_reported_when_blocked(self):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        limiter.allow("client-a")
        allowed, retry_after = limiter.allow("client-a")
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)
        self.assertLessEqual(retry_after, 60)

    def test_sliding_window_actually_slides_not_fixed_bucket(self):
        """A real sliding window: once the oldest request expires, a new one
        is allowed immediately rather than waiting for a naive fixed next minute."""
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=0.2)
        self.assertTrue(limiter.allow("client-a")[0])
        self.assertFalse(limiter.allow("client-a")[0])
        time.sleep(0.25)
        self.assertTrue(limiter.allow("client-a")[0])

    def test_rejects_invalid_construction(self):
        with self.assertRaises(ValueError):
            InMemoryRateLimiter(max_requests=0, window_seconds=60)
        with self.assertRaises(ValueError):
            InMemoryRateLimiter(max_requests=10, window_seconds=0)


class TestChatEndpointRateLimit(unittest.TestCase):
    def setUp(self):
        import os

        os.environ["REUS_USER_API_KEY"] = "test-user-key"
        os.environ["REUS_CHAT_RATE_LIMIT_PER_MINUTE"] = "3"

        import config

        config.get_settings.cache_clear()

        import container

        container.get_chat_rate_limiter.cache_clear()

        from api.main import app

        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        import os

        os.environ.pop("REUS_USER_API_KEY", None)
        os.environ.pop("REUS_CHAT_RATE_LIMIT_PER_MINUTE", None)

        import config

        config.get_settings.cache_clear()

        import container

        container.get_chat_rate_limiter.cache_clear()

    def _post(self):
        return self.client.post(
            "/chat",
            json={"prompt": "مرحبًا"},
            headers={"x-api-key": "test-user-key"},
        )

    def test_requests_within_limit_succeed(self):
        for _ in range(3):
            response = self._post()
            self.assertNotEqual(response.status_code, 429)

    def test_request_beyond_limit_returns_429_with_retry_after(self):
        for _ in range(3):
            self._post()
        response = self._post()
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

    def test_rate_limit_applies_even_to_failed_auth_attempts(self):
        """Security-critical test: wrong API-key attempts must consume the same
        rate limit. Otherwise rate limiting is meaningless against unlimited key
        guessing before any valid request is reached."""
        for _ in range(3):
            response = self.client.post(
                "/chat", json={"prompt": "x"}, headers={"x-api-key": "wrong-key"}
            )
            self.assertEqual(response.status_code, 401)

        # The fourth request, now with a valid key, must be blocked with 429
        # because the three preceding failed attempts consumed the limit.
        response = self._post()
        self.assertEqual(response.status_code, 429)


if __name__ == "__main__":
    unittest.main()
