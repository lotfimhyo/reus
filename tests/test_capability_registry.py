"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

اختبارات لـ CapabilityRegistry (infrastructure/cognitive_core/capability/
registry.py) — كانت 61% مغطاة. يغطي هذا الملف الخاصية الأهم في تصميمها
الموثَّق: إعادة تسجيل نفس (component_id, name) لا يستبدل الوصف السابق،
بل ينشئ نسخة جديدة مع إبقاء القديمة قابلة للاسترجاع — بحيث تبقى خطة
قُيِّمت مقابل النسخة v1 صالحة حتى بعد نشر v2. أيضًا: unregister يُخفي من
الاكتشاف دون حذف السجل التاريخي، والاستمرارية الفعلية عبر القرص.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest

from infrastructure.cognitive_core.capability.descriptor import RiskLevel
from infrastructure.cognitive_core.capability.exceptions import UnknownCapabilityError
from infrastructure.cognitive_core.capability.registry import CapabilityRegistry


def _register(registry, component_id="comp-a", name="do_thing", **overrides):
    kwargs = dict(
        component_id=component_id,
        name=name,
        description="does a thing",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        estimated_cost=1.0,
        risk_level=RiskLevel.LOW,
    )
    kwargs.update(overrides)
    return registry.register(**kwargs)


class TestCapabilityRegistration(unittest.TestCase):
    def setUp(self):
        self.registry = CapabilityRegistry()

    def test_register_then_get_by_id_returns_same_descriptor(self):
        descriptor = _register(self.registry)
        fetched = self.registry.get(descriptor.capability_id)
        self.assertEqual(fetched.capability_id, descriptor.capability_id)

    def test_get_unknown_id_raises_clear_error(self):
        with self.assertRaises(UnknownCapabilityError):
            self.registry.get("nonexistent-id")

    def test_reregistering_same_component_and_name_creates_a_new_version(self):
        v1 = _register(self.registry)
        v2 = _register(self.registry)  # نفس component_id/name مرة أخرى

        self.assertEqual(v1.version, 1)
        self.assertEqual(v2.version, 2)
        self.assertNotEqual(v1.capability_id, v2.capability_id)

    def test_old_version_remains_retrievable_by_id_after_a_new_version_is_published(self):
        """الخاصية الجوهرية الموثَّقة: نسخة قديمة تبقى قابلة للاسترجاع، لا
        تُستبدَل ولا تُحذَف — خطة قُيِّمت مقابلها تبقى صالحة."""
        v1 = _register(self.registry)
        _register(self.registry)  # ينشر v2

        still_there = self.registry.get(v1.capability_id)
        self.assertEqual(still_there.version, 1)

    def test_get_latest_returns_the_newest_version_only(self):
        _register(self.registry)
        v2 = _register(self.registry)

        latest = self.registry.get_latest("comp-a", "do_thing")
        self.assertEqual(latest.capability_id, v2.capability_id)

    def test_get_latest_for_unregistered_pair_raises_clear_error(self):
        with self.assertRaises(UnknownCapabilityError):
            self.registry.get_latest("ghost-comp", "ghost-name")


class TestCapabilityDiscovery(unittest.TestCase):
    def setUp(self):
        self.registry = CapabilityRegistry()

    def test_find_by_name_returns_latest_version_from_each_publishing_component(self):
        _register(self.registry, component_id="comp-a", name="translate")
        _register(self.registry, component_id="comp-b", name="translate")
        _register(self.registry, component_id="comp-a", name="unrelated")

        results = self.registry.find_by_name("translate")
        self.assertEqual({d.component_id for d in results}, {"comp-a", "comp-b"})

    def test_list_capabilities_filters_by_component(self):
        _register(self.registry, component_id="comp-a", name="x")
        _register(self.registry, component_id="comp-b", name="y")

        results = self.registry.list_capabilities(component_id="comp-a")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].component_id, "comp-a")

    def test_list_capabilities_filters_by_tag(self):
        _register(self.registry, component_id="comp-a", name="x", tags=("nlp",))
        _register(self.registry, component_id="comp-b", name="y", tags=("vision",))

        results = self.registry.list_capabilities(tag="nlp")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].component_id, "comp-a")

    def test_unregister_hides_from_discovery_but_keeps_history_retrievable(self):
        descriptor = _register(self.registry, component_id="comp-a", name="x")

        self.registry.unregister("comp-a", "x")

        self.assertEqual(self.registry.list_capabilities(), [])
        self.assertEqual(self.registry.find_by_name("x"), [])
        # لكن السجل التاريخي يبقى — للتدقيق، لا يُحذَف فعليًا
        still_retrievable = self.registry.get(descriptor.capability_id)
        self.assertEqual(still_retrievable.capability_id, descriptor.capability_id)

    def test_unregister_of_unknown_pair_does_not_raise(self):
        self.registry.unregister("ghost", "ghost")  # يجب ألا يرمي شيئًا


class TestCapabilityRegistryPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.persist_path = f"{self.tmp_dir}/capabilities.json"

    def test_a_fresh_registry_instance_restores_all_versions_and_latest_pointers(self):
        original = CapabilityRegistry(persist_path=self.persist_path)
        _register(original, component_id="comp-a", name="x")
        v2 = _register(original, component_id="comp-a", name="x")  # نسخة ثانية

        restarted = CapabilityRegistry(persist_path=self.persist_path)

        latest = restarted.get_latest("comp-a", "x")
        self.assertEqual(latest.capability_id, v2.capability_id)
        self.assertEqual(latest.version, 2)

    def test_unregister_persists_immediately(self):
        original = CapabilityRegistry(persist_path=self.persist_path)
        _register(original, component_id="comp-a", name="x")
        original.unregister("comp-a", "x")

        restarted = CapabilityRegistry(persist_path=self.persist_path)
        self.assertEqual(restarted.list_capabilities(), [])


if __name__ == "__main__":
    unittest.main()
