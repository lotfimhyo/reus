# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.telegram_link import TelegramLink


class TelegramLinkRepository(ABC):
    @abstractmethod
    def add(self, link: TelegramLink) -> None: ...

    @abstractmethod
    def get_by_chat_id(self, chat_id: str) -> TelegramLink | None: ...

    @abstractmethod
    def delete(self, chat_id: str) -> None:
        """Do not raise when no linked chat exists; unlinking is idempotent."""
        ...
