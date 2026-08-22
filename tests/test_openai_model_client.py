# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
اختبارات OpenAIModelClient. راجع ملاحظة الصدق في infrastructure/model_client.py:
هذه البيئة لا تصل شبكيًا إلى api.openai.com إطلاقًا (بغض النظر عن أي مفتاح)،
لذا تُحقن هذه الاختبارات عميل SDK وهميًا للتحقق من منطق التكامل الذي نملكه فعلًا.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from infrastructure.model_client import ModelInvocationError, OpenAIModelClient


class _FakeCompletions:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.last_call: dict | None = None

    def create(self, **kwargs):
        self.last_call = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class _FakeOpenAISDK:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(response=response, error=error))


def _chat_response(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_invoke_returns_message_content():
    fake_sdk = _FakeOpenAISDK(response=_chat_response("مرحبًا من GPT"))
    client = OpenAIModelClient(api_key="unused", client=fake_sdk)

    result = client.invoke(model_id="gpt-5", prompt="قل مرحبًا")

    assert result == "مرحبًا من GPT"


def test_invoke_sends_correct_request_shape():
    fake_sdk = _FakeOpenAISDK(response=_chat_response("ok"))
    client = OpenAIModelClient(api_key="unused", client=fake_sdk)

    client.invoke(model_id="gpt-5-mini", prompt="سؤال", max_tokens=77)

    call = fake_sdk.chat.completions.last_call
    assert call["model"] == "gpt-5-mini"
    assert call["max_tokens"] == 77
    assert call["messages"] == [{"role": "user", "content": "سؤال"}]


def test_invoke_raises_when_no_choices_returned():
    response = SimpleNamespace(choices=[])
    fake_sdk = _FakeOpenAISDK(response=response)
    client = OpenAIModelClient(api_key="unused", client=fake_sdk)

    with pytest.raises(ModelInvocationError):
        client.invoke(model_id="m", prompt="p")


def test_invoke_wraps_api_error():
    fake_request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    fake_error = openai.APIError(message="rate limited", request=fake_request, body=None)
    fake_sdk = _FakeOpenAISDK(error=fake_error)
    client = OpenAIModelClient(api_key="unused", client=fake_sdk)

    with pytest.raises(ModelInvocationError):
        client.invoke(model_id="m", prompt="p")


def test_client_construction_is_lazy_and_does_not_require_real_key():
    """لا يجب أن يفشل بناء العميل فقط لعدم وجود مفتاح حقيقي (Lazy Construction)."""
    client = OpenAIModelClient(api_key="")
    assert client is not None
