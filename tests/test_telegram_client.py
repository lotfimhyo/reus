# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Tests for TelegramClient. Because this environment has no network access to
api.telegram.org, httpx.MockTransport precisely simulates real Telegram Bot API
responses without making any live network call.
"""
from __future__ import annotations

import json as json_module

import httpx
import pytest

from infrastructure.telegram_client import TelegramAPIError, TelegramClient


def _client_with_handler(handler) -> TelegramClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(base_url="https://api.telegram.org", transport=transport)
    return TelegramClient(bot_token="test-token", http_client=http_client)


def test_send_message_posts_correct_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json_module.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {}})

    client = _client_with_handler(handler)
    client.send_message("12345", "مرحبًا من الوكيل")

    assert "test-token" in captured["url"]
    assert "sendMessage" in captured["url"]
    assert captured["json"]["chat_id"] == "12345"
    assert captured["json"]["text"] == "مرحبًا من الوكيل"


def test_send_message_truncates_to_telegram_limit():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json_module.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {}})

    client = _client_with_handler(handler)
    client.send_message("1", "x" * 5000)

    assert len(captured["json"]["text"]) == 4096


def test_send_message_raises_on_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "description": "chat not found"})

    client = _client_with_handler(handler)
    with pytest.raises(TelegramAPIError):
        client.send_message("999", "hello")


def test_get_updates_returns_parsed_results():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": [
                    {"update_id": 1, "message": {"chat": {"id": 1}, "text": "hi"}},
                ],
            },
        )

    client = _client_with_handler(handler)
    updates = client.get_updates(offset=0, timeout=1)

    assert len(updates) == 1
    assert updates[0]["update_id"] == 1


def test_get_updates_sends_offset_and_timeout():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json_module.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": []})

    client = _client_with_handler(handler)
    client.get_updates(offset=42, timeout=10)

    assert captured["json"]["offset"] == 42
    assert captured["json"]["timeout"] == 10
