# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Tests for AnthropicModelClient. Because this environment has no real
REUS_ANTHROPIC_API_KEY (see infrastructure/model_client.py), these tests inject
a fake SDK object instead of a real anthropic.Anthropic client to verify the
integration logic that is actually available: request construction, extracting
text from a response, and handling API errors—without any live network call.
"""
from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx
import pytest

from infrastructure.model_client import AnthropicModelClient, ModelInvocationError


class _FakeMessages:
    def __init__(self, response=None, error: Exception | None = None, responses: list | None = None) -> None:
        self._responses = responses  # When provided, returns them in order once per call to simulate the tool loop.
        self._response = response
        self._error = error
        self.calls: list[dict] = []
        self.last_call: dict | None = None

    def create(self, **kwargs):
        self.last_call = kwargs
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        if self._responses is not None:
            return self._responses[len(self.calls) - 1]
        return self._response


class _FakeAnthropicSDK:
    def __init__(self, response=None, error: Exception | None = None, responses: list | None = None) -> None:
        self.messages = _FakeMessages(response=response, error=error, responses=responses)


def _text_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_invoke_returns_extracted_text():
    fake_sdk = _FakeAnthropicSDK(response=_text_response("مرحبًا بك"))
    client = AnthropicModelClient(api_key="unused", client=fake_sdk)

    result = client.invoke(model_id="claude-sonnet-5", prompt="قل مرحبًا", max_tokens=100)

    assert result == "مرحبًا بك"


def test_invoke_sends_correct_request_shape():
    fake_sdk = _FakeAnthropicSDK(response=_text_response("ok"))
    client = AnthropicModelClient(api_key="unused", client=fake_sdk)

    client.invoke(model_id="claude-haiku-4-5-20251001", prompt="سؤال محدد", max_tokens=42)

    call = fake_sdk.messages.last_call
    assert call["model"] == "claude-haiku-4-5-20251001"
    assert call["max_tokens"] == 42
    assert call["messages"] == [{"role": "user", "content": "سؤال محدد"}]


def test_invoke_concatenates_multiple_text_blocks():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="جزء أول. "), SimpleNamespace(type="text", text="جزء ثانٍ.")]
    )
    fake_sdk = _FakeAnthropicSDK(response=response)
    client = AnthropicModelClient(api_key="unused", client=fake_sdk)

    result = client.invoke(model_id="m", prompt="p")

    assert result == "جزء أول. جزء ثانٍ."


def test_invoke_raises_when_no_text_blocks_returned():
    response = SimpleNamespace(content=[])
    fake_sdk = _FakeAnthropicSDK(response=response)
    client = AnthropicModelClient(api_key="unused", client=fake_sdk)

    with pytest.raises(ModelInvocationError):
        client.invoke(model_id="m", prompt="p")


def test_invoke_wraps_api_error():
    fake_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_error = anthropic.APIError(message="rate limited", request=fake_request, body=None)
    fake_sdk = _FakeAnthropicSDK(error=fake_error)
    client = AnthropicModelClient(api_key="unused", client=fake_sdk)

    with pytest.raises(ModelInvocationError):
        client.invoke(model_id="m", prompt="p")


# ---------- invoke_with_tools (tool use) ----------


def _tool_use_response(tool_name: str, tool_input: dict, tool_use_id: str = "tool_1"):
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", id=tool_use_id, name=tool_name, input=tool_input)],
    )


def _final_text_response(text: str):
    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])


def test_invoke_with_tools_returns_text_directly_when_no_tool_requested():
    fake_sdk = _FakeAnthropicSDK(response=_final_text_response("لا حاجة لأي أداة"))
    client = AnthropicModelClient(api_key="unused", client=fake_sdk)

    result = client.invoke_with_tools(
        model_id="m", prompt="p", tools=[], tool_dispatcher=lambda name, inp: None
    )

    assert result == "لا حاجة لأي أداة"
    assert len(fake_sdk.messages.calls) == 1


def test_invoke_with_tools_executes_tool_then_returns_final_answer():
    responses = [
        _tool_use_response("search_memory", {"query": "أسعار الذهب"}),
        _final_text_response("وجدت النتيجة المطلوبة"),
    ]
    fake_sdk = _FakeAnthropicSDK(responses=responses)
    client = AnthropicModelClient(api_key="unused", client=fake_sdk)

    dispatched = []

    def dispatcher(name, tool_input):
        dispatched.append((name, tool_input))
        return {"matches": []}

    result = client.invoke_with_tools(
        model_id="m", prompt="ابحث عن أسعار الذهب", tools=[{"name": "search_memory"}], tool_dispatcher=dispatcher
    )

    assert result == "وجدت النتيجة المطلوبة"
    assert dispatched == [("search_memory", {"query": "أسعار الذهب"})]
    assert len(fake_sdk.messages.calls) == 2  # First call requests the tool; second call receives the final result.


def test_invoke_with_tools_second_call_includes_tool_result():
    responses = [
        _tool_use_response("store_memory", {"content": "ملاحظة"}, tool_use_id="tu_42"),
        _final_text_response("تم الحفظ"),
    ]
    fake_sdk = _FakeAnthropicSDK(responses=responses)
    client = AnthropicModelClient(api_key="unused", client=fake_sdk)

    client.invoke_with_tools(
        model_id="m",
        prompt="احفظ هذه الملاحظة",
        tools=[{"name": "store_memory"}],
        tool_dispatcher=lambda name, inp: {"memory_id": "abc123", "status": "stored"},
    )

    second_call = fake_sdk.messages.calls[1]
    tool_result_message = second_call["messages"][-1]
    assert tool_result_message["role"] == "user"
    assert tool_result_message["content"][0]["type"] == "tool_result"
    assert tool_result_message["content"][0]["tool_use_id"] == "tu_42"


def test_invoke_with_tools_raises_after_max_iterations_without_final_answer():
    # Every response requests another tool without stopping (simulating a model that never stops).
    fake_sdk = _FakeAnthropicSDK(responses=[_tool_use_response("search_memory", {"query": "x"})] * 10)
    client = AnthropicModelClient(api_key="unused", client=fake_sdk)

    with pytest.raises(ModelInvocationError):
        client.invoke_with_tools(
            model_id="m",
            prompt="p",
            tools=[{"name": "search_memory"}],
            tool_dispatcher=lambda name, inp: {},
            max_iterations=3,
        )
    assert len(fake_sdk.messages.calls) == 3
