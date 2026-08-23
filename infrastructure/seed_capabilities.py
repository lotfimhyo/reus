# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
seed_capabilities defines real baseline capabilities, not test examples. They
are published at startup through the same AgentCapabilityBinder path, including
static restrictions and sandboxing, as any later self-built capability. Being a
default capability never grants special treatment.

Without this module, REUS_TASK_EXECUTOR=cognitive begins with an empty
capability registry and every first task is rejected for lacking a match. These
capabilities provide an immediately useful baseline.

They use seven available TemplateSynthesizer templates without requiring a
network or Ollama. Every template has at least one test case that verifies its
behavior.

The process is idempotent: find_by_name is checked before rebuilding so a
restart does not create a new version of the same capability.
"""
from __future__ import annotations

import logging

from infrastructure.agent_factory.manifest import AgentSpec, TestCase
from infrastructure.capability_binder import AgentCapabilityBinder, CapabilityBindingRejected
from infrastructure.cognitive_core.capability import CapabilityLayer

logger = logging.getLogger("reus_veritas.seed_capabilities")

DEFAULT_SPECS: list[AgentSpec] = [
    AgentSpec(
        name="uppercaser",
        capability="text.uppercase",
        description="Converts text to uppercase",
        template="uppercase",
        test_cases=[TestCase(input="hello world", expected_output="HELLO WORLD")],
    ),
    AgentSpec(
        name="lowercaser",
        capability="text.lowercase",
        description="Converts text to lowercase",
        template="lowercase",
        test_cases=[TestCase(input="HELLO WORLD", expected_output="hello world")],
    ),
    AgentSpec(
        name="reverser",
        capability="text.reverse",
        description="Reverses the order of text characters",
        template="reverse_text",
        test_cases=[TestCase(input="abc", expected_output="cba")],
    ),
    AgentSpec(
        name="word_counter",
        capability="text.word_count",
        description="Counts words in text",
        template="word_count",
        test_cases=[TestCase(input="one two three", expected_output=3)],
    ),
    AgentSpec(
        name="char_counter",
        capability="text.char_count",
        description="Counts characters in text",
        template="char_count",
        test_cases=[TestCase(input="abcd", expected_output=4)],
    ),
    AgentSpec(
        name="palindrome_checker",
        capability="text.is_palindrome",
        description="Checks whether text is a palindrome while ignoring case and symbols",
        template="is_palindrome",
        test_cases=[
            TestCase(input="a man a plan a canal panama", expected_output=True),
            TestCase(input="hello", expected_output=False),
        ],
    ),
    AgentSpec(
        name="word_sorter",
        capability="text.sort_words",
        description="Sorts text words alphabetically",
        template="sort_words",
        test_cases=[TestCase(input="banana apple cherry", expected_output="apple banana cherry")],
    ),
]


def seed_default_capabilities(
    binder: AgentCapabilityBinder,
    capability_layer: CapabilityLayer,
    specs: list[AgentSpec] = DEFAULT_SPECS,
) -> list[str]:
    """Build and bind every spec not already published by name. Return
    capabilities published in this call, or an empty list if all were present."""
    published_now: list[str] = []
    for spec in specs:
        if capability_layer.find_by_name(spec.capability):
            continue
        try:
            binder.build_and_bind(spec)
            published_now.append(spec.capability)
        except CapabilityBindingRejected as e:
            # A rejected baseline capability is a real logged error, not silent,
            # but it must not prevent other capabilities from being published.
            logger.error(
                "default_capability_rejected",
                extra={"event_name": "default_capability_rejected", "capability": spec.capability, "reason": str(e)},
            )
    return published_now
