"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

node_roles defines five ready-to-run node roles with initial capabilities.
Every node role is built through the same AgentCapabilityBinder pipeline used
for every other capability: a trusted template, static restrictions, isolated
sandboxing, and publishing. No manually inserted capability bypasses a gate.

Every role can run as a fully independent process (`scripts/run_node.py
--role=<role_id>`) and can join one distributed cluster through the existing
mTLS bootstrap and Telegram approval flow (`infrastructure/cluster_network/
bootstrap_*`) when an existing seed URL is supplied in `REUS_CLUSTER_SEED_URL`.
Independent local execution and membership in one entity, with a distributed
TrustStore and live capability sharing through `/cluster/snapshot`, are
deliberately separate properties.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from infrastructure.agent_factory.manifest import AgentSpec, TestCase
from infrastructure.seed_capabilities import DEFAULT_SPECS as _TEXT_BASE_SPECS


@dataclass(frozen=True)
class NodeRole:
    role_id: str
    label: str
    description: str
    specs: list[AgentSpec] = field(default_factory=list)


_TEXT_NODE_EXTRA = [
    AgentSpec(
        name="title_caser",
        capability="text.title_case",
        description="Converts the first letter of every word to uppercase",
        template="title_case",
        test_cases=[TestCase(input="hello world", expected_output="Hello World")],
    ),
    AgentSpec(
        name="whitespace_remover",
        capability="text.remove_whitespace",
        description="Removes all whitespace from text",
        template="remove_whitespace",
        test_cases=[TestCase(input="a b  c", expected_output="abc")],
    ),
    AgentSpec(
        name="vowel_counter",
        capability="text.vowel_count",
        description="Counts English vowels in text",
        template="vowel_count",
        test_cases=[TestCase(input="Hello World", expected_output=3)],
    ),
]

_CIPHER_NODE_SPECS = [
    AgentSpec(
        name="caesar_encoder",
        capability="cipher.caesar_encode",
        description="Encodes text with a Caesar cipher (shift 3)",
        template="caesar_encode",
        test_cases=[TestCase(input="abc", expected_output="def")],
    ),
    AgentSpec(
        name="caesar_decoder",
        capability="cipher.caesar_decode",
        description="Decodes a Caesar cipher (shift 3)",
        template="caesar_decode",
        test_cases=[TestCase(input="def", expected_output="abc")],
    ),
    AgentSpec(
        name="rle_encoder",
        capability="cipher.run_length_encode",
        description="Run-length encoding",
        template="run_length_encode",
        test_cases=[TestCase(input="aaabbc", expected_output="a3b2c1")],
    ),
    AgentSpec(
        name="rle_decoder",
        capability="cipher.run_length_decode",
        description="Run-length decoding",
        template="run_length_decode",
        test_cases=[TestCase(input="a3b2c1", expected_output="aaabbc")],
    ),
    AgentSpec(
        name="checksum_calculator",
        capability="cipher.checksum_sum",
        description="Simple checksum: sum of character values modulo 256",
        template="checksum_sum",
        test_cases=[TestCase(input="abc", expected_output=38)],
    ),
]

_NUMERIC_NODE_SPECS = [
    AgentSpec(
        name="digit_summer",
        capability="numeric.digit_sum",
        description="Sums all digits found in text",
        template="digit_sum",
        test_cases=[TestCase(input="a1b2c3", expected_output=6)],
    ),
    AgentSpec(
        name="numeric_checker",
        capability="numeric.is_numeric",
        description="Checks whether text represents an integer or decimal number",
        template="is_numeric",
        test_cases=[TestCase(input="123", expected_output=True)],
    ),
    AgentSpec(
        name="binary_converter",
        capability="numeric.decimal_to_binary",
        description="Converts a decimal number to binary without bin()",
        template="decimal_to_binary",
        test_cases=[TestCase(input=10, expected_output="1010")],
    ),
    AgentSpec(
        name="hex_converter",
        capability="numeric.decimal_to_hex",
        description="Converts a decimal number to hexadecimal without hex()",
        template="decimal_to_hex",
        test_cases=[TestCase(input=255, expected_output="ff")],
    ),
    AgentSpec(
        name="prime_checker",
        capability="numeric.is_prime",
        description="Checks whether a number is prime",
        template="is_prime",
        test_cases=[TestCase(input=17, expected_output=True)],
    ),
    AgentSpec(
        name="factorial_calculator",
        capability="numeric.factorial",
        description="Calculates the factorial of a non-negative integer",
        template="factorial",
        test_cases=[TestCase(input=5, expected_output=120)],
    ),
]

_FORMAT_NODE_SPECS = [
    AgentSpec(
        name="slugifier",
        capability="format.slugify",
        description="Converts text to a URL-safe slug",
        template="slugify",
        test_cases=[TestCase(input="Hello World!", expected_output="hello-world")],
    ),
    AgentSpec(
        name="snake_to_camel_converter",
        capability="format.snake_to_camel",
        description="Converts snake_case to camelCase",
        template="snake_to_camel",
        test_cases=[TestCase(input="hello_world", expected_output="helloWorld")],
    ),
    AgentSpec(
        name="camel_to_snake_converter",
        capability="format.camel_to_snake",
        description="Converts camelCase to snake_case",
        template="camel_to_snake",
        test_cases=[TestCase(input="helloWorld", expected_output="hello_world")],
    ),
    AgentSpec(
        name="html_tag_stripper",
        capability="format.strip_html_tags",
        description="Strips HTML tags with no nested comments or CDATA support",
        template="strip_html_tags",
        test_cases=[TestCase(input="<b>hi</b>", expected_output="hi")],
    ),
    AgentSpec(
        name="ellipsis_truncator",
        capability="format.truncate_ellipsis",
        description="Truncates long text to twenty characters and adds an ellipsis",
        template="truncate_ellipsis",
        test_cases=[TestCase(input="short", expected_output="short")],
    ),
]

_VALIDATION_NODE_SPECS = [
    AgentSpec(
        name="luhn_checker",
        capability="validation.luhn_check",
        description="Validates a number with the Luhn algorithm for card or identifier formats",
        template="luhn_check",
        test_cases=[TestCase(input="4532015112830366", expected_output=True)],
    ),
    AgentSpec(
        name="bracket_balance_checker",
        capability="validation.is_balanced_brackets",
        description="Checks whether brackets of every type are balanced in text",
        template="is_balanced_brackets",
        test_cases=[TestCase(input="([{}])", expected_output=True)],
    ),
    AgentSpec(
        name="duplicate_word_checker",
        capability="validation.has_duplicate_words",
        description="Checks whether text contains a repeated word",
        template="has_duplicate_words",
        test_cases=[TestCase(input="a b a", expected_output=True)],
    ),
    AgentSpec(
        name="unique_word_counter",
        capability="validation.count_unique_words",
        description="Counts distinct words in text",
        template="count_unique_words",
        test_cases=[TestCase(input="a a b c", expected_output=3)],
    ),
    AgentSpec(
        name="sensitive_masker",
        capability="validation.mask_sensitive_middle",
        description="Masks the middle of sensitive text, retaining its first and last two characters",
        template="mask_sensitive_middle",
        test_cases=[TestCase(input="1234567890", expected_output="12******90")],
    ),
    AgentSpec(
        name="username_validator",
        capability="validation.is_valid_username",
        description="Validates a username against simple rules",
        template="is_valid_username",
        test_cases=[TestCase(input="user_123", expected_output=True)],
    ),
]


NODE_ROLES: dict[str, NodeRole] = {
    "text-node": NodeRole(
        role_id="text-node",
        label="Text node",
        description="Core text processing: case conversion, reversal, counting, sorting, and whitespace cleanup.",
        specs=[*_TEXT_BASE_SPECS, *_TEXT_NODE_EXTRA],
    ),
    "cipher-node": NodeRole(
        role_id="cipher-node",
        label="Cipher node",
        description="Basic symbolic ciphers and encoding: Caesar, run-length, and checksum operations.",
        specs=_CIPHER_NODE_SPECS,
    ),
    "numeric-node": NodeRole(
        role_id="numeric-node",
        label="Numeric node",
        description="Numeric operations: base conversion, primality checks, factorials, and digit sums.",
        specs=_NUMERIC_NODE_SPECS,
    ),
    "format-node": NodeRole(
        role_id="format-node",
        label="Format node",
        description="Text and identifier formatting: slugs, naming conversions, HTML cleanup, and truncation.",
        specs=_FORMAT_NODE_SPECS,
    ),
    "validation-node": NodeRole(
        role_id="validation-node",
        label="Validation node",
        description="Data validation and integrity: Luhn, bracket balancing, repetition checks, masking, and identifier validation.",
        specs=_VALIDATION_NODE_SPECS,
    ),
}


def get_node_role(role_id: str) -> NodeRole:
    try:
        return NODE_ROLES[role_id]
    except KeyError:
        raise ValueError(
            f"Unknown node role: {role_id!r}. Available roles: {sorted(NODE_ROLES)}"
        ) from None
