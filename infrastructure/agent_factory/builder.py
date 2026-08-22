# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
AgentBuilder: the full self-extension pipeline.

    AgentSpec -> synthesize -> static_analyze -> sandbox test -> install

An agent is only ever installed (written to disk + made loadable) if it
clears every gate. Any failure returns a rejection with the reason, and
nothing is written to disk.
"""

import os
from dataclasses import dataclass, replace
from typing import Optional

from infrastructure.agent_factory.independent_test_reviewer import IndependentTestReviewer
from infrastructure.agent_factory.manifest import AgentSpec
from infrastructure.agent_factory.safety_checks import static_analyze
from infrastructure.agent_factory.sandbox import AgentSandbox
from infrastructure.agent_factory.synthesizer import BaseSynthesizer, TemplateSynthesizer


@dataclass
class BuildResult:
    approved: bool
    reason: str
    file_path: Optional[str] = None
    source_code: Optional[str] = None
    spec: Optional[AgentSpec] = None


class AgentBuilder:
    def __init__(
        self,
        output_dir: str = "./agents/generated",
        synthesizer: Optional[BaseSynthesizer] = None,
        sandbox: Optional[AgentSandbox] = None,
        test_reviewer: Optional[IndependentTestReviewer] = None,
    ):
        self.output_dir = output_dir
        self.synthesizer = synthesizer or TemplateSynthesizer()
        self.sandbox = sandbox or AgentSandbox()
        self.test_reviewer = test_reviewer

    def build(self, spec: AgentSpec) -> BuildResult:
        if not spec.test_cases:
            return BuildResult(False, "rejected: spec has no test cases to validate against", spec=spec)

        effective_spec = spec
        review_note = ""
        if self.test_reviewer is not None:
            try:
                extra_cases = self.test_reviewer.propose_test_cases(spec)
            except Exception as e:
                # Fail closed on ANY reviewer failure — unreachable
                # Ollama, malformed output, or anything else. A
                # configured reviewer that couldn't produce a verdict
                # must not be silently skipped.
                return BuildResult(False, f"rejected: independent test review failed ({e})", spec=spec)
            effective_spec = replace(spec, test_cases=list(spec.test_cases) + extra_cases)
            review_note = f" [{len(spec.test_cases)} original + {len(extra_cases)} independently reviewed]"

        try:
            source_code = self.synthesizer.synthesize(effective_spec)
        except Exception as e:
            return BuildResult(False, f"rejected: synthesis failed ({e})", spec=spec)

        ok, reason = static_analyze(source_code)
        if not ok:
            return BuildResult(False, f"rejected by static safety check: {reason}", source_code=source_code, spec=spec)

        sandbox_result = self.sandbox.run(source_code, effective_spec)
        if not sandbox_result.all_passed:
            return BuildResult(
                False,
                f"rejected: failed sandbox validation ({sandbox_result.summary()}){review_note}",
                source_code=source_code,
                spec=spec,
            )

        os.makedirs(self.output_dir, exist_ok=True)
        file_path = os.path.join(self.output_dir, f"{spec.name}.py")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(source_code)

        return BuildResult(
            True,
            f"approved: {sandbox_result.summary()}{review_note}",
            file_path=file_path,
            source_code=source_code,
            spec=spec,
        )

    def load_tool_instance(self, build_result: BuildResult):
        """Import the approved, on-disk generated module in the *real*
        (non-sandboxed) process and instantiate its GeneratedTool. Only
        ever call this on a BuildResult where approved=True — by this
        point the code has already cleared static + sandbox checks."""
        if not build_result.approved or not build_result.file_path:
            raise ValueError("cannot load a tool from a rejected build result")

        import importlib.util

        module_name = os.path.splitext(os.path.basename(build_result.file_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, build_result.file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.GeneratedTool()
