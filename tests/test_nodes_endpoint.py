"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Tests for the new /nodes route: a dashboard for viewing available node roles
and deployed cloud nodes, intentionally read-only. Deployment remains exclusive
to the Telegram dual-approval gate. This also proves a real bug fix discovered
through live verification: a transient cloud-provider failure previously
collapsed the whole response instead of degrading gracefully.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from infrastructure.cloud.deployment_manager import CloudDeploymentManager
from infrastructure.cloud.provider_base import CloudConfig, InstanceInfo


class TestNodesEndpoint(unittest.TestCase):
    def setUp(self):
        import os

        os.environ["REUS_API_KEY"] = "admin-test"
        import config

        config.get_settings.cache_clear()

        import container

        container.get_cloud_manager_holder.cache_clear()

        from api.main import app

        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        import os

        os.environ.pop("REUS_API_KEY", None)
        import config

        config.get_settings.cache_clear()

        import container

        container.get_cloud_manager_holder.cache_clear()

    def test_requires_admin_key(self):
        response = self.client.get("/nodes")
        self.assertEqual(response.status_code, 401)

    def test_always_lists_the_five_available_roles_even_with_no_cloud_configured(self):
        response = self.client.get("/nodes", headers={"x-api-key": "admin-test"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["available_roles"]), 5)
        role_ids = {r["role_id"] for r in body["available_roles"]}
        self.assertEqual(
            role_ids, {"text-node", "cipher-node", "numeric-node", "format-node", "validation-node"}
        )
        self.assertFalse(body["cloud_configured"])
        self.assertEqual(body["deployed_instances"], [])

    def test_reflects_real_deployed_instances_via_the_shared_holder(self):
        import container

        fake_provider = MagicMock()
        fake_provider.list_instances.return_value = [
            InstanceInfo(
                id="123", name="text-node-1", provider="digitalocean", region="nyc3",
                size="s-1vcpu-1gb", status="active", ip_address="203.0.113.5", monthly_cost_usd=6.0,
            )
        ]
        manager = CloudDeploymentManager(fake_provider)
        manager.configure(CloudConfig(
            provider="digitalocean", api_token="x", region="nyc3", size="s-1vcpu-1gb",
            max_instances=3, budget_cap_usd_per_month=50.0,
        ))
        container.get_cloud_manager_holder().manager = manager

        response = self.client.get("/nodes", headers={"x-api-key": "admin-test"})

        body = response.json()
        self.assertTrue(body["cloud_configured"])
        self.assertEqual(len(body["deployed_instances"]), 1)
        self.assertEqual(body["deployed_instances"][0]["ip_address"], "203.0.113.5")
        self.assertIsNone(body["cloud_error"])

    def test_a_transient_cloud_provider_failure_degrades_gracefully_not_500(self):
        import container

        fake_provider = MagicMock()
        fake_provider.list_instances.side_effect = RuntimeError("DigitalOcean API error (403): blocked")
        manager = CloudDeploymentManager(fake_provider)
        manager.configure(CloudConfig(
            provider="digitalocean", api_token="x", region="nyc3", size="s-1vcpu-1gb",
            max_instances=3, budget_cap_usd_per_month=50.0,
        ))
        container.get_cloud_manager_holder().manager = manager

        response = self.client.get("/nodes", headers={"x-api-key": "admin-test"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["available_roles"]), 5)
        self.assertTrue(body["cloud_configured"])
        self.assertEqual(body["deployed_instances"], [])
        self.assertIn("blocked", body["cloud_error"])


if __name__ == "__main__":
    unittest.main()
