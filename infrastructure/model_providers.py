# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
ModelProvider invokes a real model to generate a response. This is a real,
non-placeholder implementation through the official Anthropic SDK. It requires
REUS_ANTHROPIC_API_KEY; without it, the provider raises an explicit error rather
than failing silently or returning a fabricated response.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ModelProviderError(Exception):
    """Raised when a real model call fails because of a missing key, network error, or provider error."""


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
                "REUS_ANTHROPIC_API_KEY is not configured. No real model can be invoked without it."
            )
        import anthropic  # Deferred import keeps the rest of the system usable without this optional package.

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
            raise ModelProviderError(f"Model invocation failed for '{model_name}': {exc}") from exc

        text = "".join(block.text for block in response.content if block.type == "text")
        return ModelResponse(
            text=text,
            model_name=model_name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
