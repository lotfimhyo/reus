# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
TelegramClient is a direct, lightweight httpx client for the Telegram Bot API.
It sends and receives messages through long polling, which does not require a
public HTTPS webhook address.

The client follows the official Bot API request shape. In this development
environment, live Telegram connectivity is unavailable, so it is verified with
an injected httpx test double rather than a network call. A suitable runtime
environment can use it after setting REUS_TELEGRAM_BOT_TOKEN.
"""
from __future__ import annotations

import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramAPIError(Exception):
    def __init__(self, method: str, description: str):
        super().__init__(f"Telegram Bot API call failed ({method}): {description}")


class TelegramClient:
    def __init__(self, bot_token: str, http_client: httpx.Client | None = None) -> None:
        self._token = bot_token
        # HTTP-client injection enables complete tests without a network or real bot token.
        self._http = http_client or httpx.Client(base_url=TELEGRAM_API_BASE, timeout=35.0)

    def _call(self, method: str, params: dict | None = None) -> dict:
        try:
            response = self._http.post(f"/bot{self._token}/{method}", json=params or {})
        except httpx.HTTPError as exc:
            raise TelegramAPIError(method, f"Network error: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise TelegramAPIError(method, f"Invalid non-JSON response: {exc}") from exc

        if not body.get("ok", False):
            raise TelegramAPIError(method, body.get("description", "unknown error"))
        return body["result"]

    def send_message(self, chat_id: str, text: str) -> None:
        # 4,096 is Telegram's actual message-length limit; truncate rather than fail delivery.
        self._call("sendMessage", {"chat_id": chat_id, "text": text[:4096]})

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict]:
        """Long polling keeps the connection open for up to `timeout` seconds
        while waiting for messages, or returns immediately when updates exist.
        `offset` prevents receiving the same update twice."""
        params: dict = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", params)

    def close(self) -> None:
        self._http.close()
