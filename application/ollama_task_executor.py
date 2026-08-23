"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

OllamaTaskExecutor is the local-model task execution path. It fills the gap
between an `OllamaClient` used only for capability-code synthesis and an
executor that can answer actual user tasks.

**Relationship to ModelRoutingExecutor:** Ollama remains the primary route.
`ModelRoutingExecutor` for secondary API models is used only as a genuine
fallback after an `OllamaError`, such as an unavailable server or a model that
has not been pulled locally. Operators can instead choose
`REUS_TASK_EXECUTOR=model_router` explicitly when they want secondary models
without Ollama.

Every actual fallback, but never a successful Ollama call, publishes the
`task.ollama_fallback_used` event. A local-model outage and temporary API-model
replacement must be observable rather than silent.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from application.task_executor import TaskExecutionError, TaskExecutor
from domain.workflow import TaskNode
from infrastructure.agent_factory.support.ollama_client import OllamaClient, OllamaError
from infrastructure.event_bus import Event, EventBus
from infrastructure.model_promotion import ActiveModelStore

logger = logging.getLogger("reus.ollama_task_executor")


class OllamaTaskExecutor(TaskExecutor):
    def __init__(
        self,
        client: OllamaClient,
        fallback_executor: Optional[TaskExecutor] = None,
        event_bus: Optional[EventBus] = None,
        active_model_store: Optional[ActiveModelStore] = None,
    ) -> None:
        """`fallback_executor` is usually `ModelRoutingExecutor` for secondary
        API models, but any `TaskExecutor` is valid. `None` disables automatic
        fallback so an Ollama failure fails the task directly.

        When supplied, `active_model_store` is consulted for every invocation,
        not only at construction. A promotion or rollback therefore applies to
        the next task without restarting this executor or rebuilding the
        `OllamaClient`. `None` always uses the static `client.model`.
        """
        self._client = client
        self._fallback = fallback_executor
        self._bus = event_bus
        self._active_model_store = active_model_store

    def execute(self, task: TaskNode) -> Any:
        prompt = task.payload.get("prompt")
        if not prompt:
            raise TaskExecutionError(f"Task '{task.name}' has no payload prompt and cannot be routed to a model.")

        system = task.payload.get("system")
        json_mode = task.payload.get("json_mode", False)
        model_override = self._active_model_store.get_active() if self._active_model_store else None

        try:
            response_text = self._client.generate(prompt, system=system, json_mode=json_mode, model=model_override)
        except OllamaError as exc:
            return self._fallback_or_raise(task, exc)

        return {
            "model_used": model_override or self._client.model,
            "provider": "ollama",
            "response": response_text,
        }

    def _fallback_or_raise(self, task: TaskNode, original_error: OllamaError) -> Any:
        if self._fallback is None:
            raise TaskExecutionError(
                f"Ollama is unavailable and no fallback executor is configured: {original_error}"
            ) from original_error

        logger.warning("ollama_unreachable_falling_back", extra={"task_name": task.name, "error": str(original_error)})
        self._publish(
            "task.ollama_fallback_used",
            {"task_id": task.task_id, "task_name": task.name, "reason": str(original_error)},
        )
        try:
            result = self._fallback.execute(task)
        except TaskExecutionError as exc:
            raise TaskExecutionError(
                f"Ollama is unavailable ({original_error}) and the fallback executor also failed: {exc}"
            ) from exc
        except Exception as exc:  # Do not swallow unexpected fallback-executor errors.
            raise TaskExecutionError(
                f"Ollama is unavailable ({original_error}) and the fallback executor also failed: {exc}"
            ) from exc

        if isinstance(result, dict):
            result = {**result, "fallback_from": "ollama", "fallback_reason": str(original_error)}
        return result

    def _publish(self, name: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(Event(name=name, payload=payload))
