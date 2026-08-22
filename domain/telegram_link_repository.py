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
        """لا يرفع خطأ إن لم توجد محادثة مرتبطة أصلًا؛ إلغاء ربط غير موجود عملية آمنة (Idempotent)."""
        ...
