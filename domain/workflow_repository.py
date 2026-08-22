# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.workflow import Workflow


class WorkflowNotFound(Exception):
    def __init__(self, workflow_id: str):
        super().__init__(f"لم يتم العثور على Workflow بالمعرّف: {workflow_id}")


class WorkflowRepository(ABC):
    @abstractmethod
    def add(self, workflow: Workflow) -> None: ...

    @abstractmethod
    def get(self, workflow_id: str) -> Workflow: ...

    @abstractmethod
    def update(self, workflow: Workflow) -> None: ...

    @abstractmethod
    def list_all(self) -> list[Workflow]: ...
