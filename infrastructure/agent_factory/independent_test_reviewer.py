# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
IndependentTestReviewer: closes the "self-graded homework" gap flagged
repeatedly since the closing-the-loop update — the same model call that
proposes a capability's implementation (via the planner -> synthesizer
path) also proposes the test cases that implementation is judged against.
A model can, even unintentionally, write convenient code and convenient
tests that pass together while still being wrong for cases it didn't
think to test.

This class asks a SEPARATE model call, given ONLY the capability's
natural-language description — never the implementation code, never the
original test cases — to independently propose additional test cases,
specifically probing edge cases. `AgentBuilder` (when given a
`test_reviewer`) runs the sandbox against the UNION of the original and
independently-proposed test cases; every one must pass.

HONESTY ABOUT WHAT THIS DOES AND DOESN'T FIX: this is real independence
(a fresh call, blind to the implementation) but not full independence —
it's still the same underlying model/vendor as the implementer, and could
share systematic blind spots with it. True independence would use a
different model or vendor entirely. This strengthens the correctness leg
of the pipeline; it is not a complete fix, and is not claimed to be one.
"""

import json
import re
from typing import List

from infrastructure.agent_factory.manifest import AgentSpec, TestCase
from infrastructure.agent_factory.support.ollama_client import OllamaClient

_SYSTEM_PROMPT = """You are an independent QA reviewer. You are given ONLY \
a natural-language description of a function's intended behavior — you \
have NOT seen its implementation and must not assume any particular \
internal logic. Propose test cases that would catch a broken, incomplete, \
or overly narrow implementation: edge cases such as empty input, unusual \
casing, boundary values, and anything else relevant to the description.

Respond with ONLY a JSON array of objects: {"input": <value>, "expected_output": <value>}. \
No prose, no markdown fences. Propose at least 2 test cases."""


def _extract_json_array(text: str) -> str:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


class ReviewFailed(RuntimeError):
    pass


class IndependentTestReviewer:
    def __init__(self, client: OllamaClient):
        self._client = client

    def propose_test_cases(self, spec: AgentSpec) -> List[TestCase]:
        prompt = f"Capability description: {spec.description}"
        raw = self._client.generate(prompt, system=_SYSTEM_PROMPT, json_mode=True)
        json_text = _extract_json_array(raw)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            # Fail CLOSED, not open: if a reviewer was explicitly
            # configured, silently proceeding without it on a parse
            # failure would violate the guarantee the developer opted
            # into. Better to surface the failure as a rejected build.
            raise ReviewFailed(f"independent reviewer returned unparseable output: {e}") from e

        cases = []
        for item in data:
            try:
                cases.append(TestCase(input=item["input"], expected_output=item["expected_output"]))
            except (KeyError, TypeError):
                continue

        if not cases:
            raise ReviewFailed("independent reviewer proposed no usable test cases")
        return cases
