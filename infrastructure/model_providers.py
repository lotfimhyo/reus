# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
ModelProvider: يستدعي نموذجًا فعليًا لتوليد استجابة. تطبيق حقيقي (وليس Placeholder)
عبر SDK أنثروبيك الرسمي. يتطلب مفتاح API فعلي (REUS_ANTHROPIC_API_KEY) ليعمل —
بدونه يرفع خطأً واضحًا فورًا بدل فشل صامت أو استجابة وهمية.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ModelProviderError(Exception):
    """تُرفع عند فشل الاستدعاء الفعلي للنموذج (مفتاح مفقود، خطأ شبكة، خطأ من مزوّد النموذج)."""


@dataclass
class ModelResponse:
    text: str
    model_name: str
    input_tokens: int
    output_tokens: int


class ModelProvider(ABC):
    @abstractmethod
    def generate(self, model_name: str, prompt: str, max_tokens: int = 1024) -> ModelResponse: ...


class AnthropicModelProvider(ModelProvider):
    def __init__(self, api_key: str | None) -> None:
        if not api_key:
            raise ModelProviderError(
                "REUS_ANTHROPIC_API_KEY غير مُعرَّف. لا يمكن استدعاء أي نموذج فعليًا بدونه."
            )
        import anthropic  # استيراد مؤجَّل: يتيح استخدام بقية النظام حتى بلا هذه الحزمة مثبّتة اختياريًا

        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(self, model_name: str, prompt: str, max_tokens: int = 1024) -> ModelResponse:
        import anthropic

        try:
            response = self._client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise ModelProviderError(f"فشل استدعاء النموذج '{model_name}': {exc}") from exc

        text = "".join(block.text for block in response.content if block.type == "text")
        return ModelResponse(
            text=text,
            model_name=model_name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
