"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Tests for DigitalOceanProvider (infrastructure/cloud/digitalocean_provider.py),
which previously had 63% coverage. When used with real credentials, this
module can incur real costs by creating or destroying cloud servers, so it
merits deeper-than-average coverage. Every test fully mocks
``urllib.request.urlopen``; running this suite makes no network connection and
does not create or spend on cloud resources.
"""
from __future__ import annotations

import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from infrastructure.cloud.digitalocean_provider import DigitalOceanError, DigitalOceanProvider
from infrastructure.cloud.provider_base import CloudConfig


def _fake_response(payload: dict):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def _config(**overrides):
    defaults = dict(
        provider="digitalocean",
        api_token="fake-token",
        region="nyc3",
        size="s-1vcpu-1gb",
        max_instances=1,
        budget_cap_usd_per_month=20.0,
    )
    defaults.update(overrides)
    return CloudConfig(**defaults)


class TestCreateInstance(unittest.TestCase):
    def setUp(self):
        self.provider = DigitalOceanProvider()

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_create_instance_sends_correct_droplet_payload(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _fake_response({"droplet": {"id": 123, "name": "node-1", "status": "new"}}),
            _fake_response({"sizes": [{"slug": "s-1vcpu-1gb", "price_monthly": 6.0}]}),
        ]

        self.provider.create_instance("node-1", _config())

        first_call_request = mock_urlopen.call_args_list[0][0][0]
        self.assertEqual(first_call_request.full_url, "https://api.digitalocean.com/v2/droplets")
        sent_body = json.loads(first_call_request.data)
        self.assertEqual(sent_body["name"], "node-1")
        self.assertEqual(sent_body["region"], "nyc3")
        self.assertEqual(sent_body["size"], "s-1vcpu-1gb")
        self.assertNotIn("user_data", sent_body)  # No default cloud-init script.

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_create_instance_includes_user_data_when_provided(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _fake_response({"droplet": {"id": 1, "name": "n", "status": "new"}}),
            _fake_response({"sizes": []}),
        ]

        self.provider.create_instance("n", _config(user_data="#!/bin/bash\necho hi"))

        sent_body = json.loads(mock_urlopen.call_args_list[0][0][0].data)
        self.assertEqual(sent_body["user_data"], "#!/bin/bash\necho hi")

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_create_instance_returns_info_with_no_ip_yet(self, mock_urlopen):
        """A new server has no IP address immediately after creation; none must be invented."""
        mock_urlopen.side_effect = [
            _fake_response({"droplet": {"id": 123, "name": "node-1", "status": "new"}}),
            _fake_response({"sizes": [{"slug": "s-1vcpu-1gb", "price_monthly": 6.0}]}),
        ]

        info = self.provider.create_instance("node-1", _config())

        self.assertEqual(info.id, "123")
        self.assertIsNone(info.ip_address)
        self.assertEqual(info.provider, "digitalocean")
        self.assertEqual(info.monthly_cost_usd, 6.0)

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_authorization_header_carries_the_real_token(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _fake_response({"droplet": {"id": 1, "name": "n", "status": "new"}}),
            _fake_response({"sizes": []}),
        ]

        self.provider.create_instance("n", _config(api_token="super-secret-token"))

        sent_request = mock_urlopen.call_args_list[0][0][0]
        self.assertEqual(sent_request.get_header("Authorization"), "Bearer super-secret-token")


class TestListInstances(unittest.TestCase):
    def setUp(self):
        self.provider = DigitalOceanProvider()

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_extracts_the_public_ipv4_address_not_private(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response(
            {
                "droplets": [
                    {
                        "id": 1,
                        "name": "node-1",
                        "status": "active",
                        "region": {"slug": "nyc3"},
                        "size_slug": "s-1vcpu-1gb",
                        "size": {"price_monthly": 6.0},
                        "networks": {
                            "v4": [
                                {"type": "private", "ip_address": "10.0.0.5"},
                                {"type": "public", "ip_address": "203.0.113.7"},
                            ]
                        },
                    }
                ]
            }
        )

        instances = self.provider.list_instances(_config())

        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].ip_address, "203.0.113.7")

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_handles_droplet_with_no_public_ip_yet(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response(
            {
                "droplets": [
                    {
                        "id": 1,
                        "name": "node-1",
                        "status": "new",
                        "networks": {"v4": []},
                    }
                ]
            }
        )

        instances = self.provider.list_instances(_config())

        self.assertIsNone(instances[0].ip_address)

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_empty_account_returns_empty_list_not_error(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({"droplets": []})

        instances = self.provider.list_instances(_config())

        self.assertEqual(instances, [])


class TestDestroyInstance(unittest.TestCase):
    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_sends_delete_to_the_correct_droplet_id(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({})

        DigitalOceanProvider().destroy_instance("999", _config())

        sent_request = mock_urlopen.call_args[0][0]
        self.assertEqual(sent_request.get_method(), "DELETE")
        self.assertIn("/droplets/999", sent_request.full_url)


class TestEstimateMonthlyCost(unittest.TestCase):
    def setUp(self):
        self.provider = DigitalOceanProvider()

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_returns_price_for_matching_size(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response(
            {"sizes": [{"slug": "s-1vcpu-1gb", "price_monthly": 6.0}, {"slug": "s-2vcpu-2gb", "price_monthly": 12.0}]}
        )

        cost = self.provider.estimate_monthly_cost(_config(size="s-2vcpu-2gb"))

        self.assertEqual(cost, 12.0)

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_returns_zero_for_size_not_found_in_the_list(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({"sizes": [{"slug": "other-size", "price_monthly": 6.0}]})

        cost = self.provider.estimate_monthly_cost(_config(size="does-not-exist"))

        self.assertEqual(cost, 0.0)

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_returns_zero_not_raises_when_api_call_fails(self, mock_urlopen):
        """Documented behavior: 0.0 means "could not verify," not "free."
        That failure must not stop the larger operation (creating a server)."""
        mock_urlopen.side_effect = urllib.error.URLError("network down")

        cost = self.provider.estimate_monthly_cost(_config())

        self.assertEqual(cost, 0.0)


class TestErrorHandling(unittest.TestCase):
    def setUp(self):
        self.provider = DigitalOceanProvider()

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_http_error_is_wrapped_with_status_code_and_response_body(self, mock_urlopen):
        http_error = urllib.error.HTTPError(
            url="https://api.digitalocean.com/v2/droplets",
            code=422,
            msg="Unprocessable Entity",
            hdrs=None,
            fp=MagicMock(read=lambda: b'{"message": "invalid region"}'),
        )
        mock_urlopen.side_effect = http_error

        with self.assertRaises(DigitalOceanError) as ctx:
            self.provider.create_instance("n", _config())

        message = str(ctx.exception)
        self.assertIn("422", message)
        self.assertIn("invalid region", message)

    @patch("infrastructure.cloud.digitalocean_provider.urllib.request.urlopen")
    def test_network_failure_is_wrapped_not_leaked_raw(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with self.assertRaises(DigitalOceanError) as ctx:
            self.provider.list_instances(_config())

        self.assertIn("DigitalOcean API", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
