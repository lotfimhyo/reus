# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
DefaultTaskExecutor is a real TaskExecutor implementation, not a placeholder.

It verifies agent permissions, retrieves relevant semantic-memory context when
reading is permitted, and stores a task-execution summary when writing is
permitted. This provides useful, persistent context across successive tasks
without pretending to be a model-invocation executor. It remains replaceable by
an executor that calls a model through the same TaskExecutor interface.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from application.agent_service import AgentService
from application.memory_service import MemoryService, StoreMemoryCommand
from application.task_executor import TaskExecutionError, TaskExecutor
from domain.entities import PermissionDenied
from domain.repositories import AgentNotFound
from domain.workflow import TaskNode

logger = logging.getLogger("reus_veritas.worker")


class DefaultTaskExecutor(TaskExecutor):
    def __init__(self, agent_service: AgentService, memory_service: MemoryService) -> None:
        self._agents = agent_service
        self._memory = memory_service

    def execute(self, task: TaskNode) -> Any:
        if task.agent_id is None:
            if "prompt" in task.payload:
                # /chat has no agent_id by design because it is a public,
                # stateless conversation surface. The default executor requires
                # a registered agent per task, so provide configuration guidance
                # rather than an opaque unassigned-agent error.
                raise TaskExecutionError(
                    "REUS_TASK_EXECUTOR=\"default\" does not support free-text /chat. "
                    "This executor requires a pre-registered agent for every task, while /chat is deliberately "
                    "public and stateless. To enable /chat, set REUS_TASK_EXECUTOR to \"ollama\" "
                    "(requires a local Ollama server and REUS_OLLAMA_ENABLED=true) or \"model_router\" "
                    "(requires REUS_ANTHROPIC_API_KEY, REUS_OPENAI_API_KEY, or REUS_GOOGLE_API_KEY). "
                    "The \"cognitive\" executor also does not support /chat because it requires "
                    "required_capability_name or required_tags in the payload for a capability-directed task."
                )
            raise TaskExecutionError(f"Task '{task.name}' has no assigned agent and cannot be executed")

        try:
            self._agents.get_agent(task.agent_id)
        except AgentNotFound as exc:
            raise TaskExecutionError(str(exc)) from exc

        context: list[str] = []
        try:
            results = self._memory.search(task.agent_id, query=task.name, top_k=3)
            context = [r.record.content for r in results]
        except PermissionDenied:
            logger.info("worker_context_skipped_no_read_permission", extra={"event_name": "worker_context_skipped"})

        summary = f"Task '{task.name}' executed at {datetime.now(timezone.utc).isoformat()}"
        try:
            self._memory.store(
                StoreMemoryCommand(agent_id=task.agent_id, content=summary, tags=["task-execution"])
            )
        except PermissionDenied:
            logger.info("worker_result_not_stored_no_write_permission", extra={"event_name": "worker_result_skipped"})

        return {"task_name": task.name, "agent_id": task.agent_id, "context_used": context, "summary": summary}
