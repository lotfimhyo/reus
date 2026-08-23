# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
CognitiveTaskExecutor connects a TaskNode from Reus orchestration to the
CognitiveEngine cycle: analysis, candidate plans, cost/risk evaluation,
execution, and learning.

OrchestratorService and TaskWorker remain responsible only for the task DAG,
including dependencies, retries, and events. CognitiveEngine is responsible
only for how one task executes through the capability registry. Selection,
evaluation, and learning remain inside cognitive_core.

A TaskNode becomes a Goal through either payload["required_capability_name"]
or payload["required_tags"]. At least one is required; otherwise execution is
rejected explicitly rather than failing silently.

These routing keys do not reach the capability handler. CognitiveEngine passes
the complete goal payload to handlers, so leaving routing fields in it would
pollute self-built capabilities with unrelated inputs. Goal.payload therefore
contains only the fields that remain after extracting the routing keys.
"""
from __future__ import annotations

from application.task_executor import TaskExecutionError, TaskExecutor
from domain.workflow import TaskNode
from infrastructure.cognitive_core.cognitive.engine import CognitiveEngine
from infrastructure.cognitive_core.cognitive.exceptions import (
    EmptyPlanSetError,
    NoCapabilityFoundError,
)
from infrastructure.cognitive_core.cognitive.goal import Goal

_ROUTING_KEYS = ("required_capability_name", "required_tags")


class CognitiveTaskExecutor(TaskExecutor):
    """Connect TaskWorker and OrchestratorService to CognitiveEngine instead
    of DefaultTaskExecutor or direct ModelRoutingExecutor routing. Enable with
    REUS_TASK_EXECUTOR=cognitive."""

    def __init__(self, engine: CognitiveEngine, executor) -> None:
        self._engine = engine
        self._executor = executor  # Injected cognitive execution adapter.

    def execute(self, task: TaskNode):
        goal = self._build_goal(task)
        try:
            cycle = self._engine.run(goal, self._executor)
        except (NoCapabilityFoundError, EmptyPlanSetError) as exc:
            raise TaskExecutionError(str(exc)) from exc

        if not cycle.execution_result.success:
            raise TaskExecutionError(
                cycle.execution_result.error or f"Selected capability execution failed for task {task.task_id}"
            )
        return cycle.execution_result.output

    @staticmethod
    def _build_goal(task: TaskNode) -> Goal:
        required_name = task.payload.get("required_capability_name")
        required_tags = tuple(task.payload.get("required_tags", ()))
        if not required_name and not required_tags:
            raise TaskExecutionError(
                f"Task {task.task_id!r} ({task.name!r}) specifies neither "
                "required_capability_name nor required_tags in its payload; "
                "CognitiveEngine cannot match it to a capability."
            )
        clean_payload = {k: v for k, v in task.payload.items() if k not in _ROUTING_KEYS}
        return Goal(
            description=task.name,
            payload=clean_payload,
            required_capability_name=required_name,
            required_tags=required_tags,
            goal_id=task.task_id,
        )
