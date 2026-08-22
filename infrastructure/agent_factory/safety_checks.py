# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Static safety check for generated agent source code, run BEFORE the code
is ever executed (even in the sandbox). Defense in depth: this is the
first gate; `sandbox.py` (isolated subprocess + resource limits) is the
second.

Policy: generated agent code may NOT:
  - import anything at all (no `import` / `from ... import`)
  - reference dangerous builtins: eval, exec, compile, open, __import__,
    globals, locals, vars, getattr, setattr, delattr, exit, quit, breakpoint
  - access any dunder attribute (blocks sandbox-escape tricks like
    `().__class__.__bases__[0].__subclasses__()`)

This is intentionally restrictive. It means generated tools can only do
pure, self-contained logic on their input — which is exactly the class of
capability we want an autonomous code-generation pipeline building for
itself without human review of every line.
"""

import ast
from typing import Tuple

_FORBIDDEN_NAMES = {
    "eval", "exec", "compile", "open", "__import__",
    "globals", "locals", "vars",
    "getattr", "setattr", "delattr",
    "exit", "quit", "breakpoint",
}


def static_analyze(source_code: str) -> Tuple[bool, str]:
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        return False, f"syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "imports are not allowed in generated agent code"

        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            return False, f"forbidden name used: '{node.id}'"

        if isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("__") and attr.endswith("__"):
                return False, f"forbidden dunder attribute access: '{attr}'"

    return True, "ok"
