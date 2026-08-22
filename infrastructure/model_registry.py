# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
سجل النماذج الافتراضي عبر عدة مزوّدين (Anthropic, OpenAI, Google).

ملاحظة صدق مهمة: أرقام التكلفة (`input_cost_per_1k_tokens_usd` إلخ) هنا **تقديرية
نسبية لأغراض الترتيب فقط** وليست تسعيرًا رسميًا معلنًا يُعتمَد عليه في الفوترة —
يجب على أي مُشغّل إنتاجي تحديثها من صفحة تسعير كل مزوّد الرسمية الحالية قبل
الاعتماد عليها في قرارات تكلفة حقيقية. القيم هنا تحافظ فقط على الترتيب النسبي
الصحيح داخل كل عائلة نماذج (الأرخص/الأسرع أولًا، الأعلى قدرة وتكلفة أخيرًا).

ملاحظة ثانية: نماذج OpenAI وGoogle مُدرجة هنا لأن ModelRouter مصمَّم ليكون
عابرًا للمزوّدين بطبيعته — لكن العملاء الفعليين لهذين المزوّدين (راجع
infrastructure/model_client.py) لم يُتحقق منهما عبر شبكة فعلية في هذه البيئة
تحديدًا (مقيَّدة بالوصول إلى api.anthropic.com فقط)، بعكس Anthropic.
"""
from __future__ import annotations

from application.model_router import ModelProfile, ModelRouter

DEFAULT_MODEL_PROFILES: list[ModelProfile] = [
    # --- Anthropic ---
    ModelProfile(
        name="claude-haiku-4-5-20251001",
        provider="anthropic",
        capability_tags=frozenset({"chat", "summarization", "classification", "fast"}),
        input_cost_per_1k_tokens_usd=0.001,
        output_cost_per_1k_tokens_usd=0.005,
        max_context_tokens=200_000,
        relative_speed_rank=1,
    ),
    ModelProfile(
        name="claude-sonnet-5",
        provider="anthropic",
        capability_tags=frozenset({"chat", "summarization", "classification", "reasoning", "code", "fast"}),
        input_cost_per_1k_tokens_usd=0.003,
        output_cost_per_1k_tokens_usd=0.015,
        max_context_tokens=200_000,
        relative_speed_rank=2,
    ),
    ModelProfile(
        name="claude-opus-4-8",
        provider="anthropic",
        capability_tags=frozenset({"chat", "summarization", "classification", "reasoning", "code", "deep-research"}),
        input_cost_per_1k_tokens_usd=0.015,
        output_cost_per_1k_tokens_usd=0.075,
        max_context_tokens=200_000,
        relative_speed_rank=3,
    ),
    # --- OpenAI ---
    ModelProfile(
        name="gpt-5-mini",
        provider="openai",
        capability_tags=frozenset({"chat", "summarization", "classification", "fast"}),
        input_cost_per_1k_tokens_usd=0.001,
        output_cost_per_1k_tokens_usd=0.004,
        max_context_tokens=128_000,
        relative_speed_rank=1,
    ),
    ModelProfile(
        name="gpt-5",
        provider="openai",
        capability_tags=frozenset({"chat", "summarization", "classification", "reasoning", "code"}),
        input_cost_per_1k_tokens_usd=0.005,
        output_cost_per_1k_tokens_usd=0.02,
        max_context_tokens=128_000,
        relative_speed_rank=2,
    ),
    # --- Google ---
    ModelProfile(
        name="gemini-2.5-flash",
        provider="google",
        capability_tags=frozenset({"chat", "summarization", "classification", "fast"}),
        input_cost_per_1k_tokens_usd=0.0005,
        output_cost_per_1k_tokens_usd=0.003,
        max_context_tokens=1_000_000,
        relative_speed_rank=1,
    ),
    ModelProfile(
        name="gemini-2.5-pro",
        provider="google",
        capability_tags=frozenset({"chat", "summarization", "classification", "reasoning", "code", "deep-research"}),
        input_cost_per_1k_tokens_usd=0.0035,
        output_cost_per_1k_tokens_usd=0.014,
        max_context_tokens=1_000_000,
        relative_speed_rank=2,
    ),
]

KIMI_MODEL_PROFILE = ModelProfile(
    name="kimi-k3",
    provider="kimi",
    capability_tags=frozenset({"chat", "summarization", "classification", "reasoning", "code"}),
    input_cost_per_1k_tokens_usd=0.0,
    output_cost_per_1k_tokens_usd=0.0,
    max_context_tokens=256_000,
    relative_speed_rank=2,
)


def build_default_router(include_kimi: bool = False) -> ModelRouter:
    profiles = [*DEFAULT_MODEL_PROFILES]
    if include_kimi:
        profiles.append(KIMI_MODEL_PROFILE)
    return ModelRouter(profiles=profiles)
