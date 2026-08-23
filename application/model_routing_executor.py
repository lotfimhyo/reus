# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""TaskExecutor implementation that uses `ModelRouter` to choose a model from
a registered provider according to task payload and invokes it through the
provider-specific `ModelClientRegistry`. Tool use is optional.

`task.payload` accepts `prompt` (required), optional capability, context,
input-cost, preference, and maximum-token constraints, and `enable_tools`.
When tools are enabled, a task must be assigned to an agent and the executor
must receive `MemoryService`. Collaboration tools are exposed only when both
an orchestrator and agent repository are configured; delegated work still
requires the agent's `spawn:subagent` permission. The selected provider must
support `invoke_with_tools`.

The executor can replace `DefaultTaskExecutor` through `REUS_TASK_EXECUTOR`
without changes to `TaskWorker` or `OrchestratorService`.
"""
from __future__ import annotations

from typing import Any

from application.agent_tools import ALL_TOOLS, MEMORY_TOOLS, AgentToolExecutor
from application.memory_service import MemoryService
from application.model_router import ModelRouter, NoSuitableModel, TaskRequirements
from application.orchestrator_service import OrchestratorService
from application.task_executor import TaskExecutionError, TaskExecutor
from domain.repositories import AgentRepository
from domain.workflow import TaskNode
from infrastructure.model_client import ModelInvocationError, ToolUseNotSupported
from infrastructure.model_client_registry import ModelClientRegistry, UnknownProvider


class ModelRoutingExecutor(TaskExecutor):
    def __init__(
        self,
        router: ModelRouter,
        client_registry: ModelClientRegistry,
        memory_service: MemoryService | None = None,
        orchestrator: OrchestratorService | None = None,
        agent_repo: AgentRepository | None = None,
    ) -> None:
        self._router = router
        self._clients = client_registry
        self._memory_service = memory_service
        self._orchestrator = orchestrator
        self._agent_repo = agent_repo

    def execute(self, task: TaskNode) -> Any:
        prompt = task.payload.get("prompt")
        if not prompt:
            raise TaskExecutionError(f"Task '{task.name}' has no payload prompt and cannot be routed to a model.")

        requirements = TaskRequirements(
            required_capabilities=frozenset(task.payload.get("required_capabilities", [])),
            min_context_tokens=task.payload.get("min_context_tokens", 0),
            max_input_cost_per_1k_tokens_usd=task.payload.get("max_input_cost_per_1k_tokens_usd"),
            prefer=task.payload.get("prefer", "cheapest"),
        )

        try:
            model = self._router.select(requirements)
        except NoSuitableModel as exc:
            raise TaskExecutionError(str(exc)) from exc

        try:
            client = self._clients.get(model.provider)
        except UnknownProvider as exc:
            raise TaskExecutionError(str(exc)) from exc

        max_tokens = task.payload.get("max_tokens", 1024)

        if task.payload.get("enable_tools"):
            if task.agent_id is None:
                raise TaskExecutionError("Tool use requires the task to be assigned to an agent (agent_id).")
            if self._memory_service is None:
                raise TaskExecutionError("Tool use requires ModelRoutingExecutor to receive MemoryService.")

            tool_executor = AgentToolExecutor(
                memory_service=self._memory_service,
                agent_id=task.agent_id,
                orchestrator=self._orchestrator,
                agent_repo=self._agent_repo,
            )
            # Expose collaboration tools only when this executor can actually
            # fulfill them, so the model never calls a guaranteed UnknownTool.
            available_tools = ALL_TOOLS if (self._orchestrator and self._agent_repo) else MEMORY_TOOLS
            try:
                response_text = client.invoke_with_tools(
                    model_id=model.name,
                    prompt=prompt,
                    tools=[t.to_anthropic_format() for t in available_tools],
                    tool_dispatcher=tool_executor.dispatch,
                    max_tokens=max_tokens,
                )
            except (ModelInvocationError, ToolUseNotSupported) as exc:
                raise TaskExecutionError(str(exc)) from exc
        else:
            try:
                response_text = client.invoke(model_id=model.name, prompt=prompt, max_tokens=max_tokens)
            except ModelInvocationError as exc:
                raise TaskExecutionError(str(exc)) from exc

        return {"model_used": model.name, "provider": model.provider, "response": response_text}
