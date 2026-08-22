# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
OllamaSynthesizer: generates a new Tool's `run` method body using a local
Ollama model, per the user's explicit preference for an Ollama-only setup
(no Anthropic/OpenAI API calls anywhere in this path).

Nothing about the safety pipeline changes based on this: the exact same
`static_analyze` (no imports, no eval/exec/dunder-escape) and `AgentSandbox`
(isolated subprocess, resource limits, test cases) gates from
agent_factory/safety_checks.py and sandbox.py apply identically to
model-written code as to the offline TemplateSynthesizer's code. A model
gets no special trust for being a model.
"""

from infrastructure.agent_factory.manifest import AgentSpec
from infrastructure.agent_factory.support.ollama_client import OllamaClient
from infrastructure.agent_factory.synthesizer import BaseSynthesizer

_SYSTEM_PROMPT = """You write a single Python method body for a sandboxed \
tool. Rules, followed exactly:
- Output ONLY the body of `run(self, input_data)` — no class/def line, no imports, no prose, no markdown fences.
- Absolutely no `import` statements of any kind.
- No eval, exec, compile, open, __import__, getattr, setattr, delattr, globals, locals, vars.
- No dunder attribute access (anything shaped like `__name__`).
- Pure logic on `input_data` only, using bare builtins (str, int, float, list, dict, len, sorted, etc.).
- End with a `return` statement.
"""


class OllamaSynthesizer(BaseSynthesizer):
    def __init__(self, client: OllamaClient):
        self._client = client

    def synthesize(self, spec: AgentSpec) -> str:
        prompt = f"Capability to implement: {spec.description}"
        body = self._client.generate(prompt, system=_SYSTEM_PROMPT).strip()
        body = self._strip_code_fence(body)
        indented_body = "\n".join(f"        {line}" for line in body.splitlines())

        return (
            "class GeneratedTool:\n"
            f"    name = {spec.name!r}\n"
            f"    capability = {spec.capability!r}\n\n"
            "    def run(self, input_data):\n"
            f"{indented_body}\n"
        )

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:]  # drop opening fence (``` or ```python)
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines)
        return text
