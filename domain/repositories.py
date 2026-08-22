# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Repository Pattern: منفذ مجرد (Port) لا يعرف شيئًا عن آلية التخزين الفعلية.
أي تطبيق (In-Memory الآن، Postgres/Redis لاحقًا) يجب أن يلتزم بهذه الواجهة
بحيث تكون الوحدات قابلة للاستبدال دون المساس بطبقة التطبيق (Dependency Inversion).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities import Agent


class AgentNotFound(Exception):
    def __init__(self, agent_id: str):
        super().__init__(f"لم يتم العثور على وكيل بالمعرّف: {agent_id}")
        self.agent_id = agent_id


class AgentRepository(ABC):
    @abstractmethod
    def add(self, agent: Agent) -> None: ...

    @abstractmethod
    def get(self, agent_id: str) -> Agent: ...

    @abstractmethod
    def list_all(self) -> list[Agent]: ...

    @abstractmethod
    def update(self, agent: Agent) -> None: ...

    @abstractmethod
    def delete(self, agent_id: str) -> None: ...
