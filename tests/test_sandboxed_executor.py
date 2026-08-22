"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

أول اختبارات مباشرة لـ SandboxedExecutor (`infrastructure/cognitive_core/
resource/sandbox.py`) — كانت مغطاة سابقًا بشكل غير مباشر فقط عبر اختبارات
أعلى طبقة (test_node_roles، test_capability_binder، ...) دون أي اختبار
يتحقق من آلية العزل نفسها (المهلة الزمنية، حد الذاكرة، التقاط الأخطاء).

يثبت هذا الملف تحديدًا إصلاح خلل حقيقي مكتشَف بالقياس المباشر: تحويل حد
الذاكرة (`RLIMIT_AS`) من سقف مطلق إلى سقف نسبي (فوق الحجم الافتراضي الفعلي
الذي ورثته العملية الفرعية عبر fork()، مقاسًا بـVmSize لا RSS) — لم يُصلَح
هذا التعليق الحقيقي (hang) الذي كان يحدث عند تشغيل tests.test_cluster_
mtls_bootstrap ثم tests.test_node_roles في نفس العملية. الاختبار الحرج هنا
هو `test_actual_over_allocation_is_still_caught`: يتحقق أن الإصلاح لم
يُبطِل الغرض من الحد أصلًا (سقف نسبي واسع جدًا لا يعني بلا سقف).
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
        """الاختبار الحرج للإصلاح: الحد النسبي الجديد يضيف هامشًا فوق حجم
        العملية الموروث، لكن يجب أن يبقى هامشًا محدودًا فعليًا — مهمة تحاول
        حجز أضعاف الحد المسموح يجب أن تفشل، لا أن تنجح بصمت لأن الحد صار
        فضفاضًا بلا معنى."""
        def allocates_way_too_much(payload):
            # يحاول حجز ~2 جيجابايت من الذاكرة الفعلية — أكبر بكثير من أي
            # هامش نسبي معقول (memory_limit_mb=64 هنا) بصرف النظر عن حجم
            # العملية الأصلي وقت fork().
            hog = bytearray(2 * 1024 * 1024 * 1024)
            return {"len": len(hog)}

        outcome = self.executor.run(
            allocates_way_too_much, {}, timeout_seconds=10.0, memory_limit_mb=64
        )
        self.assertIn(outcome.status, ("error", "timeout"))
        if outcome.status == "error":
            self.assertIn("Memory", outcome.data)

    def test_none_memory_limit_means_no_ceiling_applied(self):
        """memory_limit_mb=None يجب أن يبقى معناه \"بلا حد\" صراحة، لا قيمة
        افتراضية مخفية — يوثّق سلوكًا موجودًا أصلًا، لم يتغيّر بالإصلاح."""
        outcome = self.executor.run(
            lambda payload: {"ok": True}, {}, timeout_seconds=5.0, memory_limit_mb=None
        )
        self.assertEqual(outcome.status, "ok")


if __name__ == "__main__":
    unittest.main()
