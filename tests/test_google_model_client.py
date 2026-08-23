# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Tests for GoogleModelClient. See the honesty note in
infrastructure/model_client.py: this environment has no network access to
googleapis.com regardless of any key, so these tests inject a fake SDK client
to verify the integration logic that is actually available.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from infrastructure.model_client import GoogleModelClient, ModelInvocationError


class _FakeModels:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.last_call: dict | None = None

    def generate_content(self, **kwargs):
        self.last_call = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class _FakeGoogleSDK:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.models = _FakeModels(response=response, error=error)


def test_invoke_returns_text():
    fake_sdk = _FakeGoogleSDK(response=SimpleNamespace(text="مرحبًا من Gemini"))
    client = GoogleModelClient(api_key="unused", client=fake_sdk)

    result = client.invoke(model_id="gemini-2.5-pro", prompt="قل مرحبًا")

    assert result == "مرحبًا من Gemini"


def test_invoke_sends_correct_request_shape():
    fake_sdk = _FakeGoogleSDK(response=SimpleNamespace(text="ok"))
    client = GoogleModelClient(api_key="unused", client=fake_sdk)

    client.invoke(model_id="gemini-2.5-flash", prompt="سؤال محدد", max_tokens=64)

    call = fake_sdk.models.last_call
    assert call["model"] == "gemini-2.5-flash"
    assert call["contents"] == "سؤال محدد"
    assert call["config"]["max_output_tokens"] == 64


def test_invoke_raises_when_no_text_returned():
    fake_sdk = _FakeGoogleSDK(response=SimpleNamespace(text=None))
    client = GoogleModelClient(api_key="unused", client=fake_sdk)

    with pytest.raises(ModelInvocationError):
        client.invoke(model_id="m", prompt="p")


def test_invoke_wraps_sdk_error():
    fake_sdk = _FakeGoogleSDK(error=RuntimeError("network unreachable"))
    client = GoogleModelClient(api_key="unused", client=fake_sdk)

    with pytest.raises(ModelInvocationError):
        client.invoke(model_id="m", prompt="p")


def test_client_construction_is_lazy_and_does_not_require_real_key():
    client = GoogleModelClient(api_key="")
    assert client is not None
