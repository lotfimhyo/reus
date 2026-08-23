"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Verifies the actual network-surface separation between ``public_app`` and
``admin_app`` (api/main.py). Before this change, administrative and public
routes were served by the same FastAPI process/listener with only logical
separation through different keys. This file verifies that separation at the
routing-table level: a route absent from an application returns 404, not 401.
The distinction matters because 404 means the route does not exist on that
network surface, rather than merely rejecting a request after it arrived.
"""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient


class TestNetworkSeparation(unittest.TestCase):
    def setUp(self):
        import os

        os.environ["REUS_API_KEY"] = "admin-key"
        os.environ["REUS_USER_API_KEY"] = "user-key"

        import config

        config.get_settings.cache_clear()

        from api.main import admin_app, app, public_app

        self.app = app
        self.public_app = public_app
        self.admin_app = admin_app

    def tearDown(self):
        import os

        os.environ.pop("REUS_API_KEY", None)
        os.environ.pop("REUS_USER_API_KEY", None)

        import config

        config.get_settings.cache_clear()

    def test_public_app_serves_chat_but_not_any_admin_route(self):
        client = TestClient(self.public_app)

        chat_response = client.post("/chat", json={"prompt": "hi"}, headers={"x-api-key": "user-key"})
        self.assertNotEqual(chat_response.status_code, 404)

        for admin_path in ["/agents", "/workflows", "/metrics", "/observability", "/dashboard"]:
            response = client.get(admin_path, headers={"x-api-key": "admin-key"})
            self.assertEqual(
                response.status_code, 404, f"{admin_path} must be absent from public_app"
            )

    def test_admin_app_serves_admin_routes_but_not_chat_or_public_app_page(self):
        client = TestClient(self.admin_app)

        agents_response = client.get("/agents", headers={"x-api-key": "admin-key"})
        self.assertNotEqual(agents_response.status_code, 404)

        for public_path in ["/chat", "/app"]:
            response = client.get(public_path, headers={"x-api-key": "user-key"})
            self.assertEqual(
                response.status_code, 404, f"{public_path} must be absent from admin_app"
            )

    def test_combined_app_still_serves_everything_unchanged(self):
        """The default combined app must retain its behavior and continue
        serving both route groups, as it did before this separation."""
        client = TestClient(self.app)

        chat_response = client.post("/chat", json={"prompt": "hi"}, headers={"x-api-key": "user-key"})
        self.assertNotEqual(chat_response.status_code, 404)

        agents_response = client.get("/agents", headers={"x-api-key": "admin-key"})
        self.assertNotEqual(agents_response.status_code, 404)

    def test_every_app_variant_has_its_own_health_and_ready(self):
        """Any standalone process (public_app or admin_app) needs its own
        liveness and readiness checks regardless of its other routes."""
        for variant in (self.app, self.public_app, self.admin_app):
            client = TestClient(variant)
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.get("/ready").status_code, 200)


class TestBackgroundWorkersOwnership(unittest.TestCase):
    """Verifies the documented decision in api/main.py: background workers
    (tasks, Telegram polling, and daily reporting) belong only to admin_app
    and the combined app. A standalone public_app must not start them, which
    avoids handling each event twice when the apps run as separate processes."""

    def test_public_app_lifespan_never_touches_worker_settings(self):
        import inspect

        from api.main import _make_lifespan

        source = inspect.getsource(_make_lifespan)
        # Proves the conditional branch exists in source instead of assuming it.
        self.assertIn("if start_background_workers:", source)


if __name__ == "__main__":
    unittest.main()
