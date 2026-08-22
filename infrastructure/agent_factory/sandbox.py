# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
AgentSandbox: executes untrusted generated code in an isolated subprocess
and runs the spec's test cases against it. Nothing is trusted until every
test case passes here.

Isolation layers (best-effort, documented honestly):
  1. Separate OS process (`subprocess`), not the calling process's memory space.
  2. `python3 -I` (isolated mode): ignores user site-packages and most env vars.
  3. Resource limits via `resource.setrlimit` on POSIX (CPU time, memory,
     process count) — a crashing or runaway candidate can't take the node down.
  4. A wall-clock timeout on top of the CPU-time limit, in case the process
     hangs on I/O rather than burning CPU.
  5. A blank, minimal environment (no inherited secrets/env vars).
  6. The code itself was already required to contain zero `import`
     statements (see safety_checks.py), so even if something slipped past
     the sandbox, it has no stdlib access beyond bare builtins.

This is NOT a substitute for real container/VM isolation (gVisor, Firecracker,
Docker with a locked-down profile) in a production deployment — for a
single-machine Stage 3 demo it is a reasonable, honest level of defense in depth.
"""

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List

from infrastructure.agent_factory.manifest import AgentSpec

_RUNNER_SCRIPT = """
import json

with open("tool_source.py", "r", encoding="utf-8") as f:
    source = f.read()

SAFE_BUILTINS = {
    "len": len, "str": str, "int": int, "float": float, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set, "range": range,
    "sum": sum, "min": min, "max": max, "sorted": sorted, "reversed": reversed,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "isinstance": isinstance, "abs": abs, "round": round,
    "ord": ord, "chr": chr,  # pure, no I/O, no reflection surface — safe to expose
    "ValueError": ValueError, "TypeError": TypeError, "Exception": Exception,
    "__build_class__": __build_class__,  # required by the `class` statement itself
    "__name__": "generated_tool_module",
}

namespace = {"__builtins__": SAFE_BUILTINS}

try:
    exec(compile(source, "generated_tool.py", "exec"), namespace)
    tool_cls = namespace["GeneratedTool"]
    instance = tool_cls()
except Exception as e:
    with open("results.json", "w") as f:
        json.dump({"load_error": str(e), "results": []}, f)
    raise SystemExit(0)

with open("test_cases.json", "r", encoding="utf-8") as f:
    test_cases = json.load(f)

results = []
for tc in test_cases:
    try:
        output = instance.run(tc["input"])
        results.append({
            "input": tc["input"],
            "output": output,
            "expected": tc["expected_output"],
            "passed": output == tc["expected_output"],
        })
    except Exception as e:
        results.append({
            "input": tc["input"],
            "error": str(e),
            "expected": tc["expected_output"],
            "passed": False,
        })

with open("results.json", "w") as f:
    json.dump({"load_error": None, "results": results}, f)
"""


def _limit_resources():
    # POSIX-only; silently skipped on platforms without `resource` (e.g. Windows).
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (2, 2))               # 2s CPU time
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)  # 256MB address space
        resource.setrlimit(resource.RLIMIT_NPROC, (4, 4))              # can't fork-bomb
    except Exception:
        pass


@dataclass
class SandboxResult:
    all_passed: bool
    load_error: str | None
    results: List[dict] = field(default_factory=list)

    def summary(self) -> str:
        if self.load_error:
            return f"failed to load: {self.load_error}"
        passed = sum(1 for r in self.results if r.get("passed"))
        return f"{passed}/{len(self.results)} test cases passed"


class AgentSandbox:
    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    def run(self, source_code: str, spec: AgentSpec) -> SandboxResult:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with open(os.path.join(tmp_dir, "tool_source.py"), "w", encoding="utf-8") as f:
                f.write(source_code)
            with open(os.path.join(tmp_dir, "test_cases.json"), "w", encoding="utf-8") as f:
                json.dump([tc.to_dict() for tc in spec.test_cases], f)
            runner_path = os.path.join(tmp_dir, "_runner.py")
            with open(runner_path, "w", encoding="utf-8") as f:
                f.write(_RUNNER_SCRIPT)

            # قصدًا أدنى بيئة ممكنة (لا أسرار موروثة)، لكن يجب أن تبقى كافية
            # فعليًا لتشغيل مفسّر بايثون نفسه على كل نظام تشغيل — اكتُشِف
            # بالتحقق الفعلي (لا افتراضًا) أن PATH بصيغة يونكس فقط
            # (`/usr/bin:/bin`) يكسر تشغيل subprocess تمامًا على ويندوز: وقت
            # تشغيل CPython على ويندوز يحتاج SystemRoot فعليًا (تحميل DLLs
            # مثل ws2_32.dll)، وصيغة PATH يونكس لا معنى لها هناك أصلًا.
            if os.name == "nt":
                env = {"SystemRoot": os.environ.get("SystemRoot", r"C:\Windows")}
                if "PATHEXT" in os.environ:
                    env["PATHEXT"] = os.environ["PATHEXT"]
            else:
                env = {"PATH": "/usr/bin:/bin"}

            kwargs = {}
            if os.name == "posix":
                kwargs["preexec_fn"] = _limit_resources

            try:
                subprocess.run(
                    [sys.executable, "-I", runner_path],
                    cwd=tmp_dir,
                    env=env,
                    timeout=self.timeout_seconds,
                    capture_output=True,
                    **kwargs,
                )
            except subprocess.TimeoutExpired:
                return SandboxResult(all_passed=False, load_error="sandbox timed out", results=[])

            results_path = os.path.join(tmp_dir, "results.json")
            if not os.path.exists(results_path):
                return SandboxResult(all_passed=False, load_error="sandbox produced no output (crashed?)", results=[])

            with open(results_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("load_error"):
                return SandboxResult(all_passed=False, load_error=data["load_error"], results=[])

            results = data["results"]
            all_passed = bool(results) and all(r.get("passed") for r in results)
            return SandboxResult(all_passed=all_passed, load_error=None, results=results)
