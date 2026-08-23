# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
TelegramPollingWorker runs a long-polling loop on a separate background thread.
It receives new Telegram messages without a public webhook address and connects
the delivery callback to TelegramService for result delivery.
"""
from __future__ import annotations

import logging
import threading

from application.telegram_service import TelegramService
from infrastructure.telegram_client import TelegramAPIError, TelegramClient

logger = logging.getLogger("reus_veritas.telegram")


class TelegramPollingWorker:
    def __init__(self, client: TelegramClient, service: TelegramService, poll_timeout: int = 25) -> None:
        self._client = client
        self._service = service
        self._poll_timeout = poll_timeout
        self._offset: int | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._service.set_delivery_callback(self._safe_send)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="telegram-polling-worker")
        self._thread.start()
        logger.info("telegram_polling_started", extra={"event_name": "telegram_polling_started"})

    def stop(self) -> None:
        """Stop the loop. An in-flight long-polling getUpdates call can take up
        to poll_timeout seconds to observe the stop request; this is expected
        behavior for a real long-polling client, not a fault. The daemon thread
        does not prevent process shutdown."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                updates = self._client.get_updates(offset=self._offset, timeout=self._poll_timeout)
            except TelegramAPIError:
                logger.exception("telegram_get_updates_failed")
                self._stop_event.wait(timeout=2.0)
                continue
            except Exception:
                # Final safety barrier: an unexpected error must not silently
                # terminate the polling thread.
                logger.exception("telegram_polling_unexpected_error")
                self._stop_event.wait(timeout=2.0)
                continue

            for update in updates:
                try:
                    self._handle_update(update)
                except Exception:
                    logger.exception("telegram_handle_update_failed", extra={"payload": {"update_id": update.get("update_id")}})

    def _handle_update(self, update: dict) -> None:
        self._offset = update["update_id"] + 1
        message = update.get("message")
        if not message or "text" not in message or "chat" not in message:
            return
        chat_id = str(message["chat"]["id"])
        text = message["text"]
        reply = self._service.handle_incoming_message(chat_id, text)
        self._safe_send(chat_id, reply)

    def _safe_send(self, chat_id: str, text: str) -> None:
        try:
            self._client.send_message(chat_id, text)
        except TelegramAPIError:
            logger.exception("telegram_send_message_failed", extra={"event_name": "telegram_send_failed"})
