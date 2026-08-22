"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

أول اختبارات لـ AnthropicModelProvider (infrastructure/model_providers.py)
— كانت 0% مغطاة. يستخدم محاكاة (mock) لعميل Anthropic لتفادي أي استدعاء
شبكي حقيقي، ويثبت: رفض بناء بلا مفتاح API، تغليف أخطاء SDK في
ModelProviderError بدل تسريبها كما هي، وبناء ModelResponse الصحيح من
استجابة ناجحة (بما في ذلك تجميع نصوص عدة كتل content).
"""
from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock


def _install_fake_anthropic_module():
    """يُدرج وحدة `anthropic` وهمية في sys.modules قبل استيراد الوحدة تحت
    الاختبار، حتى لا يحتاج بيئة الاختبار حزمة anthropic الحقيقية مُثبَّتة
    بسلوك مضبوط مسبقًا — نتحكم نحن بـ APIError وAnthropic() بالكامل."""
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
        non_text_block = MagicMock(type="tool_use")  # يجب تجاهله عند تجميع النص
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
