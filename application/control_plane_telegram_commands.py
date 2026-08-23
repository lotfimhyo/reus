"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Telegram-governed pairing for a control-plane server.  The user API key never
appears in Telegram, an audit file, a URL, or a browser response.
"""
from __future__ import annotations

import json
import secrets
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from application.telegram_service import TelegramService
from config import Settings
from infrastructure.control_plane_pairing_store import ControlPlanePairingStore


class PairingError(ValueError):
    """The requested control-plane pairing cannot be created safely."""


@dataclass(frozen=True)
class PairingRequest:
    pairing_id: str
    claim_token: str
    control_plane_url: str
    core_url: str


class ControlPlaneTelegramCommands:
    """Registers `/pair_control_plane <panel-url> <core-url>` for admin chats."""

    def __init__(
        self,
        telegram: TelegramService,
        settings: Settings,
        pairing_store: ControlPlanePairingStore,
        post_json: Callable[[str, dict], None] | None = None,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
        new_claim: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    ) -> None:
        self._telegram = telegram
        self._settings = settings
        self._store = pairing_store
        self._post_json = post_json or self._default_post_json
        self._new_id = new_id
        self._new_claim = new_claim
        telegram.register_admin_command("/pair_control_plane", self._request_pairing)

    def _request_pairing(self, chat_id: str, args: str) -> None:
        try:
            panel_url, core_url = self._parse_urls(args)
            pairing_id = f"panel-{self._new_id()}"
            record, claim = self._store.create(pairing_id, panel_url, core_url, self._settings.control_plane_pairing_ttl_seconds)
            request = PairingRequest(pairing_id=pairing_id, claim_token=claim, control_plane_url=panel_url, core_url=core_url)
            self._post_json(f"{panel_url}/api/reus/pairing/claim", {"pairing_id": pairing_id, "core_url": core_url, "claim_hash": record.claim_hash, "expires_at": record.expires_at})
        except PairingError as exc:
            self._telegram.deliver(chat_id, f"Pairing could not be created: {exc}")
            return

        self._telegram.request_approval(
            chat_id=chat_id,
            approval_id=request.pairing_id,
            description=(
                "Pair a new Reus control-plane server with this restricted public chat only. "
                f"Control plane: {request.control_plane_url} | Core: {request.core_url}. "
                "The admin key will not be sent, and the claim token will not appear in Telegram."
            ),
            on_approve=lambda: self._deliver_claim(chat_id, request),
            on_reject=lambda: None,
        )

    def _parse_urls(self, args: str) -> tuple[str, str]:
        values = args.split()
        if len(values) != 2:
            raise PairingError("Usage: /pair_control_plane <panel-url> <core-url>")
        panel_url, core_url = (self._validate_url(value) for value in values)
        return panel_url, core_url

    @staticmethod
    def _validate_url(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise PairingError("A valid http(s) URL without credentials, query, or fragment is required.")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise PairingError("Use HTTPS for every non-local address.")
        return value.rstrip("/")

    def _deliver_claim(self, chat_id: str, request: PairingRequest) -> None:
        callback = f"{request.control_plane_url}/api/reus/pairing/receive"
        record, user_key = self._store.consume_claim_and_issue_key(request.pairing_id, request.claim_token)
        self._post_json(
            callback,
            {
                "pairing_id": request.pairing_id,
                "claim_token": request.claim_token,
                "core_url": request.core_url,
                "user_api_key": user_key,
                "claim_token": request.claim_token,
                "expires_in_seconds": int(self._settings.control_plane_pairing_ttl_seconds),
            },
        )
        # The operator receives a non-secret identifier only. The claim token
        # stays server-to-server so Telegram cannot accidentally expose it.
        self._telegram.deliver(
            chat_id,
            f"Pairing authorization {record.pairing_id} was sent to the control-plane server over HTTPS. "
            "The pairing status will appear in the control plane shortly; run the command again if delivery fails.",
        )

    @staticmethod
    def _default_post_json(url: str, payload: dict) -> None:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310: URL is admin-approved and HTTPS-enforced.
            if response.status < 200 or response.status >= 300:
                raise PairingError(f"The control-plane server returned status {response.status}")
