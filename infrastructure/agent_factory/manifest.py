# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
AgentSpec: a declarative, JSON-serializable description of a capability the
system wants to add for itself: what it should do (`template` — which
synthesis strategy/logic to use), and a set of test cases it must pass
before it's trusted.

This is deliberately the *only* thing that ever crosses the network between
nodes when propagating a new agent (see network/node.py) — never raw
executable code. Each receiving node re-synthesizes and re-sandbox-tests
its own copy from this spec, so no node ever has to trust another node's
claim that "this code is safe".
"""

from dataclasses import asdict, dataclass, field
from typing import Any, List


@dataclass
class TestCase:
    input: Any
    expected_output: Any

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "TestCase":
        return TestCase(input=d["input"], expected_output=d["expected_output"])


@dataclass
class AgentSpec:
    name: str
    capability: str
    description: str
    template: str
    test_cases: List[TestCase] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "capability": self.capability,
            "description": self.description,
            "template": self.template,
            "test_cases": [tc.to_dict() for tc in self.test_cases],
        }

    @staticmethod
    def from_dict(d: dict) -> "AgentSpec":
        return AgentSpec(
            name=d["name"],
            capability=d["capability"],
            description=d["description"],
            template=d["template"],
            test_cases=[TestCase.from_dict(tc) for tc in d.get("test_cases", [])],
        )
