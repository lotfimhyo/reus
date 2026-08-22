# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

import threading

from domain.workflow import Workflow
from domain.workflow_repository import WorkflowNotFound, WorkflowRepository


class InMemoryWorkflowRepository(WorkflowRepository):
    def __init__(self) -> None:
        self._store: dict[str, Workflow] = {}
        self._lock = threading.RLock()

    def add(self, workflow: Workflow) -> None:
        with self._lock:
            self._store[workflow.workflow_id] = workflow

    def get(self, workflow_id: str) -> Workflow:
        with self._lock:
            wf = self._store.get(workflow_id)
            if wf is None:
                raise WorkflowNotFound(workflow_id)
            return wf

    def update(self, workflow: Workflow) -> None:
        with self._lock:
            if workflow.workflow_id not in self._store:
                raise WorkflowNotFound(workflow.workflow_id)
            self._store[workflow.workflow_id] = workflow

    def list_all(self) -> list[Workflow]:
        with self._lock:
            return list(self._store.values())
