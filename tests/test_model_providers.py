"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

First tests for AnthropicModelProvider (infrastructure/model_providers.py),
which previously had 0% coverage. They mock the Anthropic client to avoid any
real network call and verify that construction without an API key is rejected,
SDK errors are wrapped in ModelProviderError rather than leaking directly, and
a correct ModelResponse is built from a successful response, including joined
text from multiple content blocks.
"""
from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock


def _install_fake_anthropic_module():
    """Insert a fake ``anthropic`` module into ``sys.modules`` before importing
    the unit under test, so the test environment does not need the real package
    installed. This fixture controls ``APIError`` and ``Anthropic()`` fully."""
    fake_module = types.ModuleType("anthropic")

    class FakeAPIError(Exception):
        pass

    fake_module.APIError = FakeAPIError
    fake_module.Anthropic = MagicMock()
    sys.modules["anthropic"] = fake_module
    return fake_module


class TestAnthropicModelProvider(unittest.TestCase):
    def setUp(self):
        self.fake_anthropic = _install_fake_anthropic_module()
        from infrastructure.model_providers import AnthropicModelProvider, ModelProviderError

        self.AnthropicModelProvider = AnthropicModelProvider
        self.ModelProviderError = ModelProviderError

    def tearDown(self):
        sys.modules.pop("anthropic", None)

    def test_construction_without_api_key_raises_immediately(self):
        with self.assertRaises(self.ModelProviderError):
            self.AnthropicModelProvider(api_key=None)

    def test_construction_with_empty_string_key_also_raises(self):
        with self.assertRaises(self.ModelProviderError):
            self.AnthropicModelProvider(api_key="")

    def test_generate_wraps_sdk_api_error_not_leaks_it_raw(self):
        provider = self.AnthropicModelProvider(api_key="fake-key")
        provider._client.messages.create.side_effect = self.fake_anthropic.APIError("rate limited")

        with self.assertRaises(self.ModelProviderError) as ctx:
            provider.generate("claude-sonnet-5", "مرحبًا")
        self.assertIn("claude-sonnet-5", str(ctx.exception))

    def test_generate_builds_response_from_successful_call(self):
        provider = self.AnthropicModelProvider(api_key="fake-key")

        text_block_1 = MagicMock(type="text", text="جزء أول. ")
        text_block_2 = MagicMock(type="text", text="جزء ثانٍ.")
        non_text_block = MagicMock(type="tool_use")  # Must be ignored when joining text.
        fake_response = MagicMock()
        fake_response.content = [text_block_1, non_text_block, text_block_2]
        fake_response.usage.input_tokens = 12
        fake_response.usage.output_tokens = 34
        provider._client.messages.create.return_value = fake_response

        result = provider.generate("claude-sonnet-5", "مرحبًا", max_tokens=500)

        self.assertEqual(result.text, "جزء أول. جزء ثانٍ.")
        self.assertEqual(result.model_name, "claude-sonnet-5")
        self.assertEqual(result.input_tokens, 12)
        self.assertEqual(result.output_tokens, 34)
        provider._client.messages.create.assert_called_once_with(
            model="claude-sonnet-5",
            max_tokens=500,
            messages=[{"role": "user", "content": "مرحبًا"}],
        )


if __name__ == "__main__":
    unittest.main()
