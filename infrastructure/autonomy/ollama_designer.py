"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Designs an agent specification using a local Ollama model. The model returns
descriptive JSON only; AgentBuilder later handles generation, static analysis,
and isolation. Invalid JSON is rejected.
"""

from __future__ import annotations

import json
import re

from domain.autonomy import GeneratedAgentDraft
from infrastructure.agent_factory.manifest import AgentSpec, TestCase
from infrastructure.agent_factory.support.ollama_client import OllamaClient
from infrastructure.cognitive_core.capability.descriptor import RiskLevel
from infrastructure.cognitive_core.cognitive.goal import Goal

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_SAFE_TEMPLATE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")

_SYSTEM_PROMPT = """You design a specification for a sandboxed Reus agent.
Return ONLY one JSON object. Never return Python code, markdown, shell commands,
URLs, secrets, or prose outside JSON.
Required shape:
{
  "name": "safe_agent_name",
  "capability": "safe.capability.name",
  "description": "short capability description",
  "template": "identity",
  "test_cases": [{"input": "example", "expected_output": "example"}],
  "tags": ["tag"],
  "risk_level": "low|medium|high",
  "estimated_cost": 0.0,
  "input_schema": {"type": "string"},
  "output_schema": {"type": "string"}
}
Use only pure, sandboxable transformations. Provide at least one test case.
"""


class OllamaAgentDesigner:
    def __init__(self, client: OllamaClient) -> None:
        self._client = client

    def design(self, goal: Goal) -> GeneratedAgentDraft:
        response = self._client.generate(
            json.dumps(
                {
                    "goal": goal.description,
                    "payload": goal.payload,
                    "required_capability_name": goal.required_capability_name,
                    "required_tags": list(goal.required_tags),
                },
                ensure_ascii=False,
            ),
            system=_SYSTEM_PROMPT,
        )
        return self._parse(response)

    @staticmethod
    def _parse(response: str) -> GeneratedAgentDraft:
        try:
            data = json.loads(response)
        except json.JSONDecodeError as exc:
            raise ValueError("local designer returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("local designer response must be a JSON object")

        required_text = ("name", "capability", "description", "template")
        for key in required_text:
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ValueError(f"designer field {key!r} must be a non-empty string")
        if not _SAFE_NAME.fullmatch(data["name"]):
            raise ValueError("designer name contains unsafe characters")
        if not _SAFE_NAME.fullmatch(data["capability"]):
            raise ValueError("designer capability contains unsafe characters")
        if not _SAFE_TEMPLATE.fullmatch(data["template"]):
            raise ValueError("designer template contains unsafe characters")

        raw_cases = data.get("test_cases")
        if not isinstance(raw_cases, list) or not raw_cases:
            raise ValueError("designer must provide at least one test case")
        test_cases: list[TestCase] = []
        for case in raw_cases[:12]:
            if not isinstance(case, dict) or "input" not in case or "expected_output" not in case:
                raise ValueError("designer test case has invalid shape")
            test_cases.append(TestCase(input=case["input"], expected_output=case["expected_output"]))

        tags = data.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) and _SAFE_NAME.fullmatch(tag) for tag in tags):
            raise ValueError("designer tags contain invalid values")
        try:
            risk_level = RiskLevel(data.get("risk_level", "medium"))
        except ValueError as exc:
            raise ValueError("designer risk_level is invalid") from exc
        estimated_cost = data.get("estimated_cost", 0.0)
        if not isinstance(estimated_cost, (int, float)) or estimated_cost < 0:
            raise ValueError("designer estimated_cost must be non-negative")

        input_schema = data.get("input_schema", {})
        output_schema = data.get("output_schema", {})
        if not isinstance(input_schema, dict) or not isinstance(output_schema, dict):
            raise ValueError("designer schemas must be JSON objects")

        return GeneratedAgentDraft(
            spec=AgentSpec(
                name=data["name"],
                capability=data["capability"],
                description=data["description"],
                template=data["template"],
                test_cases=test_cases,
            ),
            tags=tuple(tags),
            risk_level=risk_level,
            estimated_cost=float(estimated_cost),
            input_schema=input_schema,
            output_schema=output_schema,
        )
