# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""TaskExecutor port defining how a task runs without exposing execution
details to `OrchestratorService` or `TaskWorker`.

Future model calls, external tools, and data pipelines implement this plugin
boundary only.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from domain.workflow import TaskNode


class TaskExecutionError(Exception):
    """Raised when task execution fails, including missing agents, insufficient
    permissions, or internal errors."""


class TaskExecutor(ABC):
    @abstractmethod
    def execute(self, task: TaskNode) -> Any:
        """Execute a task and return a JSON-serializable result or raise
        `TaskExecutionError`."""
        ...
