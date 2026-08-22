"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Run: `python3 -m unittest tests.test_node_cloud_init -v`
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from infrastructure.cloud.digitalocean_provider import DigitalOceanProvider
from infrastructure.cloud.node_cloud_init import build_node_cloud_init_script
from infrastructure.cloud.provider_base import CloudConfig


class TestNodeCloudInit(unittest.TestCase):
    def test_rejects_unknown_role_before_generating_anything(self):
        with self.assertRaises(ValueError):
            build_node_cloud_init_script(role_id="no-such-role", source_fetch_cmd="git clone x y")

    def test_rejects_empty_source_fetch_cmd(self):
        with self.assertRaises(ValueError):
            build_node_cloud_init_script(role_id="text-node", source_fetch_cmd="   ")

    def test_generates_valid_script_with_role_and_seed_url(self):
        script = build_node_cloud_init_script(
            role_id="text-node",
            source_fetch_cmd="git clone https://example.com/reus.git /opt/reus",
            seed_bootstrap_url="http://1.2.3.4:8080",
            mtls_port=9443,
            bootstrap_port=9080,
        )
        self.assertTrue(script.startswith("#!/bin/bash"))
        self.assertIn("git clone https://example.com/reus.git /opt/reus", script)
        self.assertIn("--role text-node", script)
        self.assertIn("--seed-url http://1.2.3.4:8080", script)
        self.assertIn("--mtls-port 9443", script)
        self.assertIn("--bootstrap-port 9080", script)
        self.assertIn("systemctl enable --now reus-node.service", script)

    def test_generates_script_without_seed_url_when_omitted(self):
        script = build_node_cloud_init_script(
            role_id="validation-node", source_fetch_cmd="git clone https://example.com/reus.git /opt/reus"
        )
        self.assertNotIn("--seed-url", script)


class TestDigitalOceanUserData(unittest.TestCase):
    def test_user_data_is_included_in_droplet_creation_body_when_set(self):
        captured = {}

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"droplet": {"id": 123, "name": "n", "status": "new"}}).encode()

        def fake_urlopen(req, timeout=30):
            if req.data is not None:
                captured["body"] = json.loads(req.data)
            return _FakeResponse()

        provider = DigitalOceanProvider()
        config = CloudConfig(
            provider="digitalocean",
            api_token="tok",
            region="nyc3",
            size="s-1vcpu-1gb",
            max_instances=2,
            budget_cap_usd_per_month=20.0,
            user_data="#!/bin/bash\necho hi",
        )
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            provider.create_instance("n1", config)

        self.assertEqual(captured["body"]["user_data"], "#!/bin/bash\necho hi")

    def test_user_data_omitted_from_body_when_empty(self):
        captured = {}

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"droplet": {"id": 123, "name": "n", "status": "new"}}).encode()

        def fake_urlopen(req, timeout=30):
            if req.data is not None:
                captured["body"] = json.loads(req.data)
            return _FakeResponse()

        provider = DigitalOceanProvider()
        config = CloudConfig(
            provider="digitalocean",
            api_token="tok",
            region="nyc3",
            size="s-1vcpu-1gb",
            max_instances=2,
            budget_cap_usd_per_month=20.0,
        )
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            provider.create_instance("n1", config)

        self.assertNotIn("user_data", captured["body"])


if __name__ == "__main__":
    unittest.main()
