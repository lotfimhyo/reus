# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.agent_token import AgentToken


class AgentTokenNotFound(Exception):
    def __init__(self, token_id: str):
        super().__init__(f"لم يتم العثور على رمز بالمعرّف: {token_id}")


class AgentTokenRepository(ABC):
    @abstractmethod
    def add(self, token: AgentToken) -> None: ...

    @abstractmethod
    def get_by_hash(self, token_hash: str) -> AgentToken | None:
        """يُعيد None إن لم يوجد رمز بهذا الـ hash (وليس استثناءً؛ هذا مسار تحقق عادي)."""
        ...

    @abstractmethod
    def list_by_agent(self, agent_id: str) -> list[AgentToken]: ...

    @abstractmethod
    def update(self, token: AgentToken) -> None: ...
