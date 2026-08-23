"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Direct test for a real Windows compatibility fix in AgentSandbox.run(): PATH
was previously built unconditionally in Unix format (`/usr/bin:/bin`), which
breaks subprocess execution on Windows (the CPython runtime needs SystemRoot).
This test proves that both paths (POSIX and Windows) build the correct
environment for their platform by mocking os.name rather than relying on the
operating system that runs the test.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from infrastructure.agent_factory.manifest import AgentSpec
from infrastructure.agent_factory.sandbox import AgentSandbox


class TestSandboxEnvironmentIsPlatformAppropriate(unittest.TestCase):
    def _run_and_capture_env(self):
        captured = {}
        original_run = __import__("subprocess").run

        def spy(*args, **kwargs):
            captured["env"] = kwargs.get("env")
            return original_run(*args, **kwargs)

        spec = AgentSpec(name="x", capability="x", description="x", template="x", test_cases=[])
        with patch("infrastructure.agent_factory.sandbox.subprocess.run", side_effect=spy):
            AgentSandbox(timeout_seconds=2.0).run("def run(x): return x", spec)
        return captured.get("env")

    @patch("infrastructure.agent_factory.sandbox.os.name", "nt")
    def test_windows_env_uses_systemroot_not_unix_path(self):
        env = self._run_and_capture_env()
        self.assertIn("SystemRoot", env)
        self.assertNotIn("PATH", env)  # Never use Unix format on Windows.

    @patch("infrastructure.agent_factory.sandbox.os.name", "posix")
    def test_posix_env_is_unchanged_from_before_the_fix(self):
        env = self._run_and_capture_env()
        self.assertEqual(env, {"PATH": "/usr/bin:/bin"})


if __name__ == "__main__":
    unittest.main()
