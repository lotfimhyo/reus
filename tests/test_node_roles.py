"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

يثبت أن كل عقدة من العقد الخمس تُبنى فعليًا (لا افتراضًا) عبر
AgentCapabilityBinder الحقيقي — بما يشمل sandbox معزول حقيقي لكل حالة
اختبار مُعرَّفة في AgentSpec — ثم يُنفَّذ كل قدرة منشورة فعليًا عبر
LocalExecutor على مدخل حقيقي، متحقّقًا من المخرج الصحيح. لا شيء هنا محاكى.

Run: `python3 -m unittest tests.test_node_roles -v`
"""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from infrastructure.agent_factory.builder import AgentBuilder
from infrastructure.capability_binder import AgentCapabilityBinder
from infrastructure.cognitive_core.capability.capability_layer import CapabilityLayer
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.node_roles import NODE_ROLES, get_node_role


@dataclass(frozen=True)
class _FakeStep:
    capability_id: str


class TestNodeRoles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp_root = Path(self._tmp.name)
        self.audit_log = AppendOnlyAuditLog(str(tmp_root / "audit.jsonl"))
        self.capabilities = CapabilityLayer(self.audit_log, data_dir=str(tmp_root / "capabilities"))
        self.executor = LocalExecutor()
        self.builder = AgentBuilder(output_dir=str(tmp_root / "agents" / "generated"))
        self.binder = AgentCapabilityBinder(
            builder=self.builder, capability_layer=self.capabilities, local_executor=self.executor
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_five_roles_are_defined_with_nonempty_skillsets(self):
        self.assertEqual(len(NODE_ROLES), 5)
        for role_id, role in NODE_ROLES.items():
            self.assertTrue(role.specs, f"role {role_id!r} has no skills")

    def test_get_node_role_rejects_unknown_role(self):
        with self.assertRaises(ValueError):
            get_node_role("no-such-role")

    def test_every_role_builds_publishes_and_executes_all_its_skills(self):
        total_executed = 0
        for role_id, role in NODE_ROLES.items():
            with self.subTest(role=role_id):
                for spec in role.specs:
                    descriptor = self.binder.build_and_bind(spec)
                    self.assertTrue(self.executor.is_registered(descriptor.capability_id))

                    # كل AgentSpec يحمل حالة اختبار حقيقية على الأقل — نعيد
                    # تشغيلها هنا عبر LocalExecutor (وليس فقط عبر sandbox
                    # البناء) لإثبات أن القدرة المنشورة فعليًا صحيحة السلوك.
                    first_case = spec.test_cases[0]
                    result = self.executor(
                        _FakeStep(capability_id=descriptor.capability_id), {"input": first_case.input}
                    )
                    self.assertTrue(result.success, f"{spec.capability} failed: {result.error}")
                    self.assertEqual(result.output, first_case.expected_output)
                    total_executed += 1

        self.assertEqual(total_executed, sum(len(r.specs) for r in NODE_ROLES.values()))
        self.assertGreaterEqual(total_executed, 30)


if __name__ == "__main__":
    unittest.main()
