"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

اختبارات لـ TemplateSynthesizer وLLMSynthesizer (infrastructure/
agent_factory/synthesizer.py) — كانت 61% مغطاة، وLLMSynthesizer تحديدًا
غير مغطاة إطلاقًا. يُختبَر التوليد بالقالب بتنفيذ الكود المُولَّد فعليًا
(لا فحص نصي سطحي فقط)، وLLMSynthesizer عبر محاكاة عميل Anthropic.
"""
from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock

from infrastructure.agent_factory.manifest import AgentSpec
from infrastructure.agent_factory.synthesizer import LLMSynthesizer, TemplateSynthesizer


class TestTemplateSynthesizer(unittest.TestCase):
    def setUp(self):
        self.synthesizer = TemplateSynthesizer()

    def test_synthesize_produces_working_code_for_a_known_template(self):
        spec = AgentSpec(
            name="uppercaser", capability="text.upper", description="uppercases text", template="uppercase"
        )
        source = self.synthesizer.synthesize(spec)

        namespace: dict = {}
        exec(source, namespace)  # الكود المُولَّد نفسه، لا نسخة يدوية منه
        tool = namespace["GeneratedTool"]()
        self.assertEqual(tool.run("hello"), "HELLO")
        self.assertEqual(tool.name, "uppercaser")
        self.assertEqual(tool.capability, "text.upper")

    def test_synthesize_correctly_embeds_multiline_template_bodies(self):
        """قوالب متعددة الأسطر (مثل is_palindrome) يجب أن تُدمَج بمسافات
        بادئة صحيحة تُنتِج كودًا صالحًا قابلًا للتنفيذ، لا نصًا مشوَّهًا."""
        spec = AgentSpec(
            name="pal", capability="text.palindrome", description="checks palindrome", template="is_palindrome"
        )
        source = self.synthesizer.synthesize(spec)

        namespace: dict = {}
        exec(source, namespace)
        tool = namespace["GeneratedTool"]()
        self.assertTrue(tool.run("A man a plan a canal Panama"))
        self.assertFalse(tool.run("not a palindrome"))

    def test_unknown_template_raises_value_error_listing_known_ones(self):
        spec = AgentSpec(name="x", capability="x", description="x", template="does_not_exist")
        with self.assertRaises(ValueError) as ctx:
            self.synthesizer.synthesize(spec)
        self.assertIn("does_not_exist", str(ctx.exception))
        self.assertIn("uppercase", str(ctx.exception))  # قائمة القوالب المعروفة مُدرَجة

    def test_available_templates_is_sorted_and_non_empty(self):
        templates = TemplateSynthesizer.available_templates()
        self.assertEqual(templates, sorted(templates))
        self.assertIn("uppercase", templates)
        self.assertIn("is_prime", templates)


def _install_fake_anthropic_module():
    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = MagicMock()
    sys.modules["anthropic"] = fake_module
    return fake_module


class TestLLMSynthesizer(unittest.TestCase):
    def setUp(self):
        self.fake_anthropic = _install_fake_anthropic_module()

    def tearDown(self):
        sys.modules.pop("anthropic", None)

    def test_synthesize_extracts_and_concatenates_text_blocks_only(self):
        synthesizer = LLMSynthesizer(model="claude-sonnet-5")

        text_block_1 = MagicMock(type="text", text="return str(input_data)")
        non_text_block = MagicMock(type="tool_use")  # يجب تجاهله
        fake_response = MagicMock()
        fake_response.content = [text_block_1, non_text_block]
        synthesizer._client.messages.create.return_value = fake_response

        spec = AgentSpec(name="echo", capability="text.echo", description="echoes input", template="n/a")
        source = synthesizer.synthesize(spec)

        self.assertIn("return str(input_data)", source)
        self.assertIn("class GeneratedTool:", source)
        self.assertIn("name = 'echo'", source)

    def test_synthesize_sends_the_capability_description_in_the_prompt(self):
        synthesizer = LLMSynthesizer()
        fake_response = MagicMock()
        fake_response.content = [MagicMock(type="text", text="return None")]
        synthesizer._client.messages.create.return_value = fake_response

        spec = AgentSpec(
            name="x", capability="x.y", description="a very specific capability description", template="n/a"
        )
        synthesizer.synthesize(spec)

        call_kwargs = synthesizer._client.messages.create.call_args.kwargs
        sent_prompt = call_kwargs["messages"][0]["content"]
        self.assertIn("a very specific capability description", sent_prompt)


if __name__ == "__main__":
    unittest.main()
