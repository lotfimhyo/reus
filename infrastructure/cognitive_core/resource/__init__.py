"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Layer 2 — Resource & Execution Layer.

Public surface: other layers must depend only on the symbols exported here.
"""

from infrastructure.cognitive_core.resource.exceptions import (
    SchedulerShutDownError,
    VeritasResourceError,
)
from infrastructure.cognitive_core.resource.local_executor import HandlerResult, LocalExecutor
from infrastructure.cognitive_core.resource.monitor import ResourceMonitor, ResourceSnapshot
from infrastructure.cognitive_core.resource.sandbox import SandboxedExecutor, SandboxOutcome
from infrastructure.cognitive_core.resource.scheduler import TaskScheduler

__all__ = [
    "ResourceMonitor",
    "ResourceSnapshot",
    "SandboxedExecutor",
    "SandboxOutcome",
    "TaskScheduler",
    "LocalExecutor",
    "HandlerResult",
    "VeritasResourceError",
    "SchedulerShutDownError",
]
