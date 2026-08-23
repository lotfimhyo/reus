"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

First direct tests for SandboxedExecutor (infrastructure/cognitive_core/
resource/sandbox.py). It was previously covered only indirectly by higher-
level tests such as test_node_roles and test_capability_binder, without tests
of the isolation mechanism itself: timeouts, memory limits, and exception
capture.

This file specifically verifies a measured fix: changing the ``RLIMIT_AS``
memory limit from an absolute ceiling to a relative ceiling above the baseline
size inherited by the forked child process, measured through VmSize rather
than RSS. The fix addressed a real hang when tests.test_cluster_mtls_bootstrap
and tests.test_node_roles ran in the same process. The critical test,
``test_actual_over_allocation_is_still_caught``, verifies that the correction
does not defeat the limit's purpose; a very wide relative ceiling is not no
ceiling.
"""
from __future__ import annotations

import unittest

from infrastructure.cognitive_core.resource.sandbox import SandboxedExecutor


class TestSandboxedExecutor(unittest.TestCase):
    def setUp(self):
        self.executor = SandboxedExecutor()

    def test_successful_task_returns_ok_with_output(self):
        outcome = self.executor.run(
            lambda payload: {"doubled": payload["n"] * 2},
            {"n": 21},
            timeout_seconds=5.0,
        )
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.data, {"doubled": 42})

    def test_task_exception_is_captured_not_raised_to_caller(self):
        def raises(payload):
            raise ValueError("سبب فشل حقيقي داخل المهمة")

        outcome = self.executor.run(raises, {}, timeout_seconds=5.0)
        self.assertEqual(outcome.status, "error")
        self.assertIn("ValueError", outcome.data)

    def test_hanging_task_is_terminated_on_timeout(self):
        def hangs(payload):
            import time

            time.sleep(30)
            return {"unreachable": True}

        outcome = self.executor.run(hangs, {}, timeout_seconds=1.0)
        self.assertEqual(outcome.status, "timeout")

    def test_actual_over_allocation_is_still_caught(self):
        """Critical regression test: the new relative limit adds headroom
        above the inherited process size, but the headroom must remain finite.
        A task allocating multiples of the allowed limit must fail rather than
        silently succeeding because the limit became meaningless."""
        def allocates_way_too_much(payload):
            # Attempt to reserve ~2 GiB of memory, far beyond any reasonable
            # relative headroom (memory_limit_mb=64 here) regardless of the
            # parent-process size at fork time.
            hog = bytearray(2 * 1024 * 1024 * 1024)
            return {"len": len(hog)}

        outcome = self.executor.run(
            allocates_way_too_much, {}, timeout_seconds=10.0, memory_limit_mb=64
        )
        self.assertIn(outcome.status, ("error", "timeout"))
        if outcome.status == "error":
            self.assertIn("Memory", outcome.data)

    def test_none_memory_limit_means_no_ceiling_applied(self):
        """memory_limit_mb=None must explicitly continue to mean "no limit,"
        not an implicit default; this documents existing behavior unchanged by
        the correction."""
        outcome = self.executor.run(
            lambda payload: {"ok": True}, {}, timeout_seconds=5.0, memory_limit_mb=None
        )
        self.assertEqual(outcome.status, "ok")


if __name__ == "__main__":
    unittest.main()
