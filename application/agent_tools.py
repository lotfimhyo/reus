# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""Expose existing system capabilities as JSON-Schema tools for models that
support tool use. These are real implementations, not placeholders.

Memory tools (`search_memory`, `store_memory`) pass through `MemoryService`,
which enforces `read:memory` and `write:memory`. Collaboration tools
(`create_task`, `list_agents`) pass through `OrchestratorService` and
`AgentRepository` and enforce `spawn:subagent`. No tool can grant authority an
agent does not already possess.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from application.memory_service import MemoryService, StoreMemoryCommand
from application.orchestrator_service import CreateWorkflowCommand, OrchestratorService
from domain.entities import PermissionDenied
from domain.repositories import AgentNotFound, AgentRepository
from domain.workflow import TaskSpec


class UnknownTool(Exception):
    def __init__(self, tool_name: str):
        super().__init__(f"Unknown tool: '{tool_name}'")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict

    def to_anthropic_format(self) -> dict:
        """Format the tool for the Anthropic Messages API `tools` field."""
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


SEARCH_MEMORY_TOOL = ToolSpec(
    name="search_memory",
    description="Search the agent's semantic memory for passages relevant to a topic or question.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search text."},
            "top_k": {"type": "integer", "description": "Maximum results (default: 5)."},
        },
        "required": ["query"],
    },
)

STORE_MEMORY_TOOL = ToolSpec(
    name="store_memory",
    description="Store new information or a note in the agent's semantic memory for later retrieval.",
    input_schema={
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Content to store."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional classification tags."},
        },
        "required": ["content"],
    },
)

MEMORY_TOOLS: list[ToolSpec] = [SEARCH_MEMORY_TOOL, STORE_MEMORY_TOOL]


CREATE_TASK_TOOL = ToolSpec(
    name="create_task",
    description=(
        "Create a task executed through the system orchestrator. Assign it to the current "
        "agent for multi-step planning or to another agent by ID for real delegation. "
        "Requires the 'spawn:subagent' permission."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task_name": {"type": "string", "description": "Short task name."},
            "prompt": {"type": "string", "description": "Instruction or request to execute as a task."},
            "target_agent_id": {
                "type": "string",
                "description": "Agent ID that executes the task. Leave empty to assign the current agent.",
            },
        },
        "required": ["task_name", "prompt"],
    },
)

LIST_AGENTS_TOOL = ToolSpec(
    name="list_agents",
    description="List available agents (ID, name, state) to choose a collaboration delegate. Requires 'spawn:subagent'.",
    input_schema={"type": "object", "properties": {}, "required": []},
)

COLLABORATION_TOOLS: list[ToolSpec] = [CREATE_TASK_TOOL, LIST_AGENTS_TOOL]

ALL_TOOLS: list[ToolSpec] = MEMORY_TOOLS + COLLABORATION_TOOLS


class AgentToolExecutor:
    """Execute tool calls for one bound agent identity per routing request.

    Binding prevents a model error or manipulation from passing a different
    `agent_id`. When the optional orchestrator and repository are absent, only
    memory tools are available and collaboration-tool calls raise `UnknownTool`.
    """

    def __init__(
        self,
        memory_service: MemoryService,
        agent_id: str,
        orchestrator: OrchestratorService | None = None,
        agent_repo: AgentRepository | None = None,
    ) -> None:
        self._memory_service = memory_service
        self._agent_id = agent_id
        self._orchestrator = orchestrator
        self._agent_repo = agent_repo

    def dispatch(self, tool_name: str, tool_input: dict) -> dict[str, Any]:
        handler = self._handlers().get(tool_name)
        if handler is None:
            raise UnknownTool(tool_name)
        return handler(tool_input)

    def _handlers(self) -> dict[str, Callable[[dict], dict[str, Any]]]:
        handlers: dict[str, Callable[[dict], dict[str, Any]]] = {
            "search_memory": self._search_memory,
            "store_memory": self._store_memory,
        }
        if self._orchestrator is not None and self._agent_repo is not None:
            handlers["create_task"] = self._create_task
            handlers["list_agents"] = self._list_agents
        return handlers

    def _search_memory(self, tool_input: dict) -> dict[str, Any]:
        try:
            results = self._memory_service.search(
                agent_id=self._agent_id,
                query=tool_input.get("query", ""),
                top_k=tool_input.get("top_k", 5),
            )
        except (PermissionDenied, AgentNotFound) as exc:
            return {"error": str(exc)}
        return {
            "matches": [
                {"memory_id": r.record.memory_id, "content": r.record.content, "score": r.score} for r in results
            ]
        }

    def _store_memory(self, tool_input: dict) -> dict[str, Any]:
        try:
            record = self._memory_service.store(
                StoreMemoryCommand(
                    agent_id=self._agent_id,
                    content=tool_input.get("content", ""),
                    tags=tool_input.get("tags", []),
                )
            )
        except (PermissionDenied, AgentNotFound) as exc:
            return {"error": str(exc)}
        return {"memory_id": record.memory_id, "status": "stored"}

    def _require_spawn_permission(self) -> dict[str, Any] | None:
        """Return a ready error dictionary when spawn permission is absent, or
        `None` when it is available."""
        try:
            agent = self._agent_repo.get(self._agent_id)
        except AgentNotFound as exc:
            return {"error": str(exc)}
        if "spawn:subagent" not in agent.permissions:
            return {"error": f"Agent '{self._agent_id}' lacks the 'spawn:subagent' permission required for this tool."}
        return None

    def _create_task(self, tool_input: dict) -> dict[str, Any]:
        denial = self._require_spawn_permission()
        if denial is not None:
            return denial

        target_agent_id = tool_input.get("target_agent_id") or self._agent_id
        task_name = tool_input.get("task_name", "delegated-task")
        prompt = tool_input.get("prompt", "")

        try:
            workflow = self._orchestrator.create_workflow(
                CreateWorkflowCommand(
                    name=f"tool:{self._agent_id}:{task_name}",
                    tasks=[TaskSpec(name=task_name, agent_id=target_agent_id, payload={"prompt": prompt})],
                )
            )
        except AgentNotFound as exc:
            return {"error": str(exc)}

        task_id = next(iter(workflow.tasks.keys()))
        return {
            "workflow_id": workflow.workflow_id,
            "task_id": task_id,
            "assigned_to": target_agent_id,
            "status": "created",
        }

    def _list_agents(self, tool_input: dict) -> dict[str, Any]:
        denial = self._require_spawn_permission()
        if denial is not None:
            return denial

        agents = self._agent_repo.list_all()
        return {"agents": [{"agent_id": a.agent_id, "name": a.name, "state": a.state.value} for a in agents]}
