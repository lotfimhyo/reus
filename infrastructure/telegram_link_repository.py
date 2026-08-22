# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

import threading

from domain.telegram_link import TelegramLink
from domain.telegram_link_repository import TelegramLinkRepository


class InMemoryTelegramLinkRepository(TelegramLinkRepository):
    def __init__(self) -> None:
        self._store: dict[str, TelegramLink] = {}
        self._lock = threading.RLock()

    def add(self, link: TelegramLink) -> None:
        with self._lock:
            self._store[link.chat_id] = link

    def get_by_chat_id(self, chat_id: str) -> TelegramLink | None:
        with self._lock:
            return self._store.get(chat_id)

    def delete(self, chat_id: str) -> None:
        with self._lock:
            self._store.pop(chat_id, None)
