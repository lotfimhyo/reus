# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
seed_capabilities: مجموعة قدرات أساسية حقيقية (لا أمثلة اختبار) تُنشَر عند
الإقلاع عبر نفس مسار AgentCapabilityBinder — أي أنها تمرّ بنفس بوابات الأمان
(فحص ثابت + sandbox) تمامًا كأي قدرة يبنيها النظام لنفسه لاحقًا. لا معاملة
خاصة لهذه القدرات لكونها "افتراضية".

بدون هذا الملف: REUS_TASK_EXECUTOR=cognitive يبدأ بسجل قدرات فارغ تمامًا —
أي مهمة أولى ستُرفض حتمًا بـ"لا قدرة مطابقة". هذا يوفر خط أساس عملي فورًا.

مبني على قوالب TemplateSynthesizer السبعة المتوفرة فعليًا (بلا حاجة لشبكة أو
Ollama)؛ كل قالب أضيف بحالة اختبار واحدة على الأقل تُثبت سلوكه فعليًا وليس
افتراضًا.

Idempotent: يتحقق أولًا عبر find_by_name قبل إعادة البناء، فلا يُنشئ نسخة
(version) جديدة من نفس القدرة عند كل إعادة تشغيل.
"""
from __future__ import annotations

import logging

from infrastructure.agent_factory.manifest import AgentSpec, TestCase
from infrastructure.capability_binder import AgentCapabilityBinder, CapabilityBindingRejected
from infrastructure.cognitive_core.capability import CapabilityLayer

logger = logging.getLogger("reus_veritas.seed_capabilities")

DEFAULT_SPECS: list[AgentSpec] = [
    AgentSpec(
        name="uppercaser",
        capability="text.uppercase",
        description="يحوّل نصًا إلى حروف كبيرة",
        template="uppercase",
        test_cases=[TestCase(input="hello world", expected_output="HELLO WORLD")],
    ),
    AgentSpec(
        name="lowercaser",
        capability="text.lowercase",
        description="يحوّل نصًا إلى حروف صغيرة",
        template="lowercase",
        test_cases=[TestCase(input="HELLO WORLD", expected_output="hello world")],
    ),
    AgentSpec(
        name="reverser",
        capability="text.reverse",
        description="يعكس ترتيب أحرف النص",
        template="reverse_text",
        test_cases=[TestCase(input="abc", expected_output="cba")],
    ),
    AgentSpec(
        name="word_counter",
        capability="text.word_count",
        description="يعدّ عدد الكلمات في نص",
        template="word_count",
        test_cases=[TestCase(input="one two three", expected_output=3)],
    ),
    AgentSpec(
        name="char_counter",
        capability="text.char_count",
        description="يعدّ عدد الأحرف في نص",
        template="char_count",
        test_cases=[TestCase(input="abcd", expected_output=4)],
    ),
    AgentSpec(
        name="palindrome_checker",
        capability="text.is_palindrome",
        description="يتحقق هل النص طردي (palindrome) بتجاهل الحالة والرموز",
        template="is_palindrome",
        test_cases=[
            TestCase(input="a man a plan a canal panama", expected_output=True),
            TestCase(input="hello", expected_output=False),
        ],
    ),
    AgentSpec(
        name="word_sorter",
        capability="text.sort_words",
        description="يرتّب كلمات النص أبجديًا",
        template="sort_words",
        test_cases=[TestCase(input="banana apple cherry", expected_output="apple banana cherry")],
    ),
]


def seed_default_capabilities(
    binder: AgentCapabilityBinder,
    capability_layer: CapabilityLayer,
    specs: list[AgentSpec] = DEFAULT_SPECS,
) -> list[str]:
    """يبني ويربط كل قدرة في specs لم تُنشَر باسمها من قبل. يُعيد أسماء القدرات
    التي نُشرت فعليًا في هذا الاستدعاء (فارغة إن كانت كلها منشورة مسبقًا)."""
    published_now: list[str] = []
    for spec in specs:
        if capability_layer.find_by_name(spec.capability):
            continue
        try:
            binder.build_and_bind(spec)
            published_now.append(spec.capability)
        except CapabilityBindingRejected as e:
            # فشل بناء قدرة أساسية خطأ حقيقي يستحق الظهور في السجلات، لا إسكاتًا صامتًا،
            # لكنه لا يجب أن يمنع بقية القدرات الأخرى من النشر.
            logger.error(
                "default_capability_rejected",
                extra={"event_name": "default_capability_rejected", "capability": spec.capability, "reason": str(e)},
            )
    return published_now
