"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

First direct tests for OllamaClient (infrastructure/agent_factory/support/
ollama_client.py), which had 30% coverage. According to the module's own
documentation, it is the only client actually enabled in the "self-routing"
path (Project Phoenix). It is tested here by mocking urllib.request.urlopen,
with no live network connection because the logic under test is request
construction and response interpretation, not the transport layer.
"""
from __future__ import annotations

import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from infrastructure.agent_factory.support.ollama_client import OllamaClient, OllamaError


def _fake_response(payload: dict):
    """Simulates the response object returned by urlopen inside `with ... as resp`."""
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


class TestOllamaClientGenerate(unittest.TestCase):
    def setUp(self):
        self.client = OllamaClient(base_url="http://localhost:11434", model="llama3.1")

    @patch("infrastructure.agent_factory.support.ollama_client.urllib.request.urlopen")
    def test_generate_returns_the_response_text(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({"response": "مرحبًا بك"})

        result = self.client.generate("قل مرحبًا")

        self.assertEqual(result, "مرحبًا بك")

    @patch("infrastructure.agent_factory.support.ollama_client.urllib.request.urlopen")
    def test_generate_builds_correct_request_url_and_body(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({"response": "ok"})

        self.client.generate("test prompt")

        sent_request = mock_urlopen.call_args[0][0]
        self.assertEqual(sent_request.full_url, "http://localhost:11434/api/generate")
        sent_body = json.loads(sent_request.data)
        self.assertEqual(sent_body["model"], "llama3.1")
        self.assertEqual(sent_body["prompt"], "test prompt")
        self.assertFalse(sent_body["stream"])
        self.assertNotIn("system", sent_body)
        self.assertNotIn("format", sent_body)

    @patch("infrastructure.agent_factory.support.ollama_client.urllib.request.urlopen")
    def test_generate_includes_system_prompt_when_given(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({"response": "ok"})

        self.client.generate("test", system="be concise")

        sent_body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(sent_body["system"], "be concise")

    @patch("infrastructure.agent_factory.support.ollama_client.urllib.request.urlopen")
    def test_generate_sets_json_format_when_json_mode_true(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({"response": "{}"})

        self.client.generate("test", json_mode=True)

        sent_body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(sent_body["format"], "json")

    @patch("infrastructure.agent_factory.support.ollama_client.urllib.request.urlopen")
    def test_generate_model_override_replaces_default_for_this_call_only(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({"response": "ok"})

        self.client.generate("test", model="evolved-model-v2")

        sent_body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(sent_body["model"], "evolved-model-v2")
        self.assertEqual(self.client.model, "llama3.1")  # The default did not change.

    @patch("infrastructure.agent_factory.support.ollama_client.urllib.request.urlopen")
    def test_generate_returns_empty_string_when_response_key_missing(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({})  # No response key at all.

        result = self.client.generate("test")

        self.assertEqual(result, "")

    @patch("infrastructure.agent_factory.support.ollama_client.urllib.request.urlopen")
    def test_generate_wraps_connection_failure_with_a_helpful_message(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with self.assertRaises(OllamaError) as ctx:
            self.client.generate("test")

        message = str(ctx.exception)
        self.assertIn("localhost:11434", message)
        self.assertIn("llama3.1", message)
        self.assertIn("ollama pull", message)


class TestOllamaClientReachability(unittest.TestCase):
    def setUp(self):
        self.client = OllamaClient()

    @patch("infrastructure.agent_factory.support.ollama_client.urllib.request.urlopen")
    def test_returns_true_when_server_responds(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({})
        self.assertTrue(self.client.is_reachable())

    @patch("infrastructure.agent_factory.support.ollama_client.urllib.request.urlopen")
    def test_returns_false_instead_of_raising_when_unreachable(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        self.assertFalse(self.client.is_reachable())


if __name__ == "__main__":
    unittest.main()
