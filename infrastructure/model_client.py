"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

ModelClient separates the mechanism for invoking a model over the network from
the ModelRouter decision of which model to choose. Clients are injectable so
surrounding behavior can be tested without a real network.

This module supports Anthropic, OpenAI, and Google behind one interface, with
tool-use invocation where a provider client implements it.

Each client uses its provider's official SDK, but live invocation requires a
valid API key and network access to that provider. In this development
environment, network access is restricted: Anthropic is available, while
OpenAI and Google live calls have not been verified here. The OpenAI and Google
clients are nevertheless covered through injected SDK doubles, like the
Anthropic client. A production environment with suitable network access may use
them after setting the relevant API key.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

import anthropic

logger = logging.getLogger("reus_veritas.model_client")


class ModelInvocationError(Exception):
    """Raised when a real model invocation fails because of network, authentication, or API errors."""


class ToolUseNotSupported(Exception):
    def __init__(self, provider: str):
        super().__init__(f"Provider '{provider}' does not support tool use in this application yet")


class ModelClient(ABC):
    @abstractmethod
    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        """Invoke a model and return generated text, or raise ModelInvocationError."""
        ...

    def invoke_with_tools(
        self,
        model_id: str,
        prompt: str,
        tools: list[dict],
        tool_dispatcher: Callable[[str, dict], Any],
        max_tokens: int = 1024,
        max_iterations: int = 5,
    ) -> str:
        """Run a complete tool loop: invoke the model; when it requests a tool,
        execute it through tool_dispatcher; then return the result to the model
        until it produces final text or reaches max_iterations. The base method
        raises ToolUseNotSupported; only concrete implementations support it."""
        raise ToolUseNotSupported(self.__class__.__name__)


class AnthropicModelClient(ModelClient):
    def __init__(self, api_key: str, client: anthropic.Anthropic | None = None) -> None:
        # Client injection enables complete tests without a real API key or network.
        self._client = client or anthropic.Anthropic(api_key=api_key)

    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        try:
            response = self._client.messages.create(
                model=model_id,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise ModelInvocationError(f"Model invocation failed for '{model_id}': {exc}") from exc

        return self._extract_text(response, model_id)

    def invoke_with_tools(
        self,
        model_id: str,
        prompt: str,
        tools: list[dict],
        tool_dispatcher: Callable[[str, dict], Any],
        max_tokens: int = 1024,
        max_iterations: int = 5,
    ) -> str:
        messages: list[dict] = [{"role": "user", "content": prompt}]

        for _ in range(max_iterations):
            try:
                response = self._client.messages.create(
                    model=model_id, max_tokens=max_tokens, messages=messages, tools=tools
                )
            except anthropic.APIError as exc:
                raise ModelInvocationError(f"Model invocation failed for '{model_id}': {exc}") from exc

            if response.stop_reason != "tool_use":
                return self._extract_text(response, model_id)

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                logger.info(
                    "tool_use_invoked", extra={"event_name": "tool_use", "payload": {"tool": block.name}}
                )
                result = tool_dispatcher(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": str(result)}
                )
            messages.append({"role": "user", "content": tool_results})

        raise ModelInvocationError(
            f"Model '{model_id}' exceeded the maximum tool-use iterations ({max_iterations}) without final text"
        )

    @staticmethod
    def _extract_text(response: Any, model_id: str) -> str:
        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        if not text_blocks:
            raise ModelInvocationError(f"Model '{model_id}' returned no text content")
        return "".join(text_blocks)


class OpenAIModelClient(ModelClient):
    """OpenAI client using the official SDK; see the module note on this
    environment's live-network verification boundary."""

    def __init__(self, api_key: str, client: Any = None) -> None:
        self._api_key = api_key
        self._injected_client = client
        self._client: Any = None  # Construct lazily at the first real use.

    def _get_client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        if self._client is None:
            import openai

            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        import openai as openai_module

        try:
            response = self._get_client().chat.completions.create(
                model=model_id,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except openai_module.APIError as exc:
            raise ModelInvocationError(f"Model invocation failed for '{model_id}': {exc}") from exc

        choice = response.choices[0] if response.choices else None
        content = getattr(getattr(choice, "message", None), "content", None) if choice else None
        if not content:
            raise ModelInvocationError(f"Model '{model_id}' returned no text content")
        return content


class KimiModelClient(OpenAIModelClient):
    """Kimi client through its official OpenAI-compatible interface.

    This client grants Kimi no tool or local-execution capability. It generates
    text only when a developer explicitly enables the provider as a secondary
    model path.
    """

    def __init__(self, api_key: str, base_url: str, client: Any = None) -> None:
        super().__init__(api_key=api_key, client=client)
        self._base_url = base_url.rstrip("/")

    def _get_client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        if self._client is None:
            import openai

            self._client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client


class GoogleModelClient(ModelClient):
    """Google client using the official google-genai SDK for Gemini models;
    see the module note on this environment's live-network verification boundary."""

    def __init__(self, api_key: str, client: Any = None) -> None:
        self._api_key = api_key
        self._injected_client = client
        self._client: Any = None  # Construct lazily at the first real use.

    def _get_client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        try:
            response = self._get_client().models.generate_content(
                model=model_id,
                contents=prompt,
                config={"max_output_tokens": max_tokens},
            )
        except Exception as exc:  # google-genai does not expose one stable exception hierarchy.
            raise ModelInvocationError(f"Model invocation failed for '{model_id}': {exc}") from exc

        text = getattr(response, "text", None)
        if not text:
            raise ModelInvocationError(f"Model '{model_id}' returned no text content")
        return text
