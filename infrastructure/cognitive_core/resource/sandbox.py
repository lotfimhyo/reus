"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

SandboxedExecutor — runs a single task in an isolated OS process with a
hard memory ceiling and a wall-clock timeout, per master architecture doc
section 2.2 (executing tasks in an isolated environment) and the vision doc's Security
principle of containing failures.

Design decision: multiprocessing.Process (not threads, not asyncio) was
chosen because a thread cannot be forcibly killed if a task hangs or spins,
and cannot have its own memory ceiling — only a separate OS process can be
terminated unconditionally and have RLIMIT_AS enforced by the kernel. This
is a real, load-bearing sandbox: a task that hangs is killed on timeout, and
a task that over-allocates memory is stopped by the kernel via RLIMIT_AS.

Note: this relies on the platform's fork-based multiprocessing start method
(the default on Linux), which lets arbitrary local functions/closures be
used as tasks without needing to be pickle-importable. On platforms where
the default start method is "spawn" (e.g. Windows), task functions would
need to be top-level, picklable callables instead.

Historical incident, now fixed at the mechanism level (kept for context,
not as an open issue): a hosting process with a large memory footprint by
the time a task forks (e.g. one that has loaded an mTLS server, Flask, and
crypto libraries) used to be able to exceed a hardcoded absolute
`RLIMIT_AS` before the forked child did any work of its own — the child
died with `MemoryError` immediately, failed to even report that error
(reporting itself requires allocating), and never exited cleanly, hanging
the parent's `process.join()` indefinitely. First surfaced and diagnosed
for `infrastructure.cognitive_core.cluster`'s own process (~210MB
baseline), it was originally patched only for that one entrypoint by
raising its default ceiling to 512MB (see `cluster/__main__.py`'s
`--handler-memory-limit-mb`). That was a symptom patch, not a fix — this
project's own test suite reproduced the identical hang from a different
call site (running `tests.test_cluster_mtls_bootstrap` and
`tests.test_node_roles` together in one process; see
`scripts/run_tests_isolated.sh` for the workaround that was necessary
until this was root-caused). The actual fix, applied in `_worker` below:
measure this child's own baseline RSS immediately after fork, and apply
`memory_limit_mb` as headroom *on top of* that baseline rather than as an
absolute number blind to whatever the parent had already loaded. This
makes the limit self-adjusting per call site instead of a constant that
has to be hand-tuned upward every time a heavier host process is
discovered to need it.
"""

from __future__ import annotations

import multiprocessing
import threading
from dataclasses import dataclass
from typing import Any, Callable, Literal

try:
    import resource as _resource  # POSIX only

    _HAS_RLIMIT = hasattr(_resource, "RLIMIT_AS")
except ImportError:  # pragma: no cover - non-POSIX platforms
    _resource = None
    _HAS_RLIMIT = False

# Serializes this process's own fork attempts — see module docstring.
_fork_lock = threading.Lock()

OutcomeStatus = Literal["ok", "error", "timeout"]


@dataclass(frozen=True)
class SandboxOutcome:
    """The raw result of running one task inside the sandbox."""

    status: OutcomeStatus
    data: Any  # the task's return value on "ok", an error message otherwise


def _current_vsz_bytes() -> int:
    """The child's own virtual address space size, right after fork — the
    same unit RLIMIT_AS caps. NOT ru_maxrss/RSS: a process can have a much
    larger virtual size than resident size (thread stacks, shared library
    mappings, SSL/socket buffers all reserve address space without all of
    it being resident) — confirmed empirically in this project: a process
    that had run an mTLS test showed RSS of ~49MB but VmSize of ~427MB.
    Baselining off RSS would still under-estimate the real ceiling needed.
    Returns 0 (no adjustment) if /proc is unavailable (non-Linux)."""
    try:
        with open("/proc/self/status", "r", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmSize:"):
                    return int(line.split()[1]) * 1024  # KB -> bytes
    except OSError:
        pass
    return 0


def _worker(
    fn: Callable[[dict], dict],
    payload: dict,
    memory_limit_mb: int | None,
    result_queue: "multiprocessing.Queue",
) -> None:
    try:
        if memory_limit_mb is not None and _HAS_RLIMIT:
            # Root-cause fix (previously: hardcoded absolute ceiling — see
            # historical incident below). RLIMIT_AS must bound how much
            # THIS TASK is allowed to allocate on top of whatever fork()
            # already copy-on-write-inherited from the parent — not an
            # absolute number blind to the parent's own footprint. A
            # parent that has loaded a lot (e.g. an mTLS server, Flask,
            # crypto libraries, live threads with reserved stacks) can
            # already have a virtual address space larger than a low
            # absolute ceiling before the child does anything at all,
            # which previously caused the child to fail (either an
            # immediate MemoryError it then couldn't even report, since
            # reporting itself requires allocating, or a hang inside an
            # allocation call that blocks instead of raising under
            # overcommit) and never exit cleanly — hanging the parent's
            # process.join() forever. Measuring baseline here, in the
            # child, right after fork, makes the limit self-adjusting to
            # whatever the actual hosting process looks like.
            #
            # Historical incident (kept for record, no longer the live
            # mechanism): this exact failure mode was first diagnosed
            # empirically for infrastructure.cognitive_core.cluster's own
            # process (~210MB baseline vs. a 256MB ceiling), and patched
            # there only, by raising that one entrypoint's default to
            # 512MB (cluster/__main__.py's --handler-memory-limit-mb).
            # That was a symptom patch, not a fix — this project's own
            # test suite reproduced the identical hang from a different
            # call site (running tests.test_cluster_mtls_bootstrap and
            # tests.test_node_roles together in one process; see
            # scripts/run_tests_isolated.sh for the workaround that was
            # necessary until this was root-caused). A first attempt at
            # this fix baselined off RSS (ru_maxrss) and did NOT resolve
            # the hang — direct measurement showed why: RLIMIT_AS caps
            # virtual address space, and this project's own mTLS test
            # left VmSize at ~427MB while RSS was only ~49MB. Baselining
            # off the correct metric (VmSize) is what actually fixes it.
            baseline_bytes = _current_vsz_bytes()
            limit_bytes = baseline_bytes + memory_limit_mb * 1024 * 1024
            _resource.setrlimit(_resource.RLIMIT_AS, (limit_bytes, limit_bytes))
        output = fn(payload)
        result_queue.put(("ok", output))
    except MemoryError as exc:
        result_queue.put(("error", f"MemoryError: task exceeded its memory limit ({exc})"))
    except Exception as exc:  # noqa: BLE001 - a task's own error is data, not our bug
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


class SandboxedExecutor:
    """Runs a single (fn, payload) pair in its own process with resource
    limits enforced by the OS kernel."""

    def run(
        self,
        fn: Callable[[dict], dict],
        payload: dict,
        timeout_seconds: float = 30.0,
        memory_limit_mb: int | None = 256,
    ) -> SandboxOutcome:
        ctx = multiprocessing.get_context()
        result_queue: multiprocessing.Queue = ctx.Queue()
        process = ctx.Process(
            target=_worker, args=(fn, payload, memory_limit_mb, result_queue)
        )
        # Serialize the actual fork() against this process's own other
        # SandboxedExecutor forks — see module docstring for what this
        # does and does not protect against.
        with _fork_lock:
            process.start()
        process.join(timeout_seconds)

        if process.is_alive():
            process.terminate()
            process.join()
            return SandboxOutcome(
                status="timeout",
                data=f"Task exceeded timeout of {timeout_seconds}s and was terminated.",
            )

        if result_queue.empty():
            return SandboxOutcome(
                status="error",
                data=f"Task process exited with code {process.exitcode} "
                "before producing a result (likely killed by the OS).",
            )

        status, data = result_queue.get()
        return SandboxOutcome(status=status, data=data)
