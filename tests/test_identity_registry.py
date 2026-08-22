"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

أول اختبارات مباشرة لـ IdentityRegistry — جدول جذر الثقة الذي تعتمد عليه
كل طبقة أخرى للتحقق من "من يستدعيني فعليًا" قبل الوثوق بأي طلب موقَّع.
كانت 57% مغطاة فقط. يغطي هذا الملف: التسجيل والبحث، رفض مكوّن غير مسجَّل
(UnknownComponentError، لا فشل صامت)، التحقق من توقيع فاعل حقيقي مقابل
هوية مسجَّلة (بما في ذلك رفض توقيع منتحِل)، وأهم ما فيه: **جولة استمرارية
حقيقية على القرص** — بناء سجل جديد تمامًا (لا نفس الكائن) من نفس الملف
والتحقق أن كل هوية مسجَّلة تُستعاد فعليًا.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest

from infrastructure.cognitive_core.identity.exceptions import UnknownComponentError
from infrastructure.cognitive_core.identity.identity import ComponentIdentity
from infrastructure.cognitive_core.identity.registry import IdentityRegistry


class TestIdentityRegistryInMemory(unittest.TestCase):
    def setUp(self):
        self.registry = IdentityRegistry()

    def test_register_then_get_returns_the_same_manifest(self):
        identity = ComponentIdentity.create("agent")
        self.registry.register(identity)

        manifest = self.registry.get(identity.component_id)
        self.assertEqual(manifest.public_key_hex, identity.public_key_hex)
        self.assertEqual(manifest.component_type, "agent")

    def test_get_unregistered_component_raises_clear_error_not_keyerror(self):
        with self.assertRaises(UnknownComponentError):
            self.registry.get("nonexistent-id")

    def test_is_registered_reflects_actual_state(self):
        identity = ComponentIdentity.create("tool")
        self.assertFalse(self.registry.is_registered(identity.component_id))
        self.registry.register(identity)
        self.assertTrue(self.registry.is_registered(identity.component_id))

    def test_register_is_idempotent_by_component_id(self):
        identity = ComponentIdentity.create("agent")
        self.registry.register(identity)
        self.registry.register(identity)  # نفس component_id مرتين
        self.assertEqual(len(self.registry.list_components()), 1)

    def test_list_components_filters_by_type(self):
        agent = ComponentIdentity.create("agent")
        tool = ComponentIdentity.create("tool")
        self.registry.register(agent)
        self.registry.register(tool)

        agents_only = self.registry.list_components(component_type="agent")
        self.assertEqual(len(agents_only), 1)
        self.assertEqual(agents_only[0].component_id, agent.component_id)


class TestVerifyActorSignature(unittest.TestCase):
    def setUp(self):
        self.registry = IdentityRegistry()
        self.identity = ComponentIdentity.create("agent")
        self.registry.register(self.identity)

    def test_returns_true_for_a_genuine_signature(self):
        payload = b"execute task X"
        signature = self.identity.sign(payload)
        self.assertTrue(
            self.registry.verify_actor_signature(self.identity.component_id, payload, signature)
        )

    def test_returns_false_for_a_forged_signature_not_raises(self):
        impostor = ComponentIdentity.create("agent")
        payload = b"execute task X"
        forged_signature = impostor.sign(payload)  # وقّعه مكوّن آخر تمامًا

        result = self.registry.verify_actor_signature(
            self.identity.component_id, payload, forged_signature
        )
        self.assertFalse(result)

    def test_raises_unknown_component_for_unregistered_actor(self):
        with self.assertRaises(UnknownComponentError):
            self.registry.verify_actor_signature("ghost-id", b"payload", b"signature")


class TestIdentityRegistryPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.persist_path = f"{self.tmp_dir}/identities.json"

    def test_a_fresh_registry_instance_restores_all_registered_identities(self):
        """الاختبار الأهم هنا: لا نفس الكائن — سجل جديد تمامًا من الملف،
        يحاكي إعادة تشغيل حقيقية للعملية."""
        original_registry = IdentityRegistry(persist_path=self.persist_path)
        agent = ComponentIdentity.create("agent")
        tool = ComponentIdentity.create("tool")
        original_registry.register(agent)
        original_registry.register(tool)

        restarted_registry = IdentityRegistry(persist_path=self.persist_path)

        self.assertTrue(restarted_registry.is_registered(agent.component_id))
        self.assertTrue(restarted_registry.is_registered(tool.component_id))
        self.assertEqual(
            restarted_registry.get(agent.component_id).public_key_hex, agent.public_key_hex
        )

    def test_restored_registry_can_still_verify_signatures_correctly(self):
        """لا يكفي أن البيانات تُستعاد شكليًا — يجب أن يبقى المفتاح العام
        المُستعاد صالحًا فعليًا للتحقق من توقيعات حقيقية بعد إعادة التحميل."""
        original_registry = IdentityRegistry(persist_path=self.persist_path)
        agent = ComponentIdentity.create("agent")
        original_registry.register(agent)

        restarted_registry = IdentityRegistry(persist_path=self.persist_path)
        payload = b"post-restart task"
        signature = agent.sign(payload)

        self.assertTrue(
            restarted_registry.verify_actor_signature(agent.component_id, payload, signature)
        )

    def test_registry_with_no_persist_path_never_touches_disk(self):
        import os

        registry = IdentityRegistry()  # لا persist_path
        registry.register(ComponentIdentity.create("agent"))
        self.assertFalse(os.path.exists(self.persist_path))


if __name__ == "__main__":
    unittest.main()
