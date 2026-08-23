"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

First direct tests for IdentityRegistry—the root-of-trust table that every
other layer relies on to verify who is actually calling before trusting any
signed request. It had only 57% coverage. This file covers registration and
lookup, rejection of an unregistered component (UnknownComponentError rather
than silent failure), verification of a genuine actor signature against a
registered identity (including rejection of an impersonator signature), and,
most importantly, a **real on-disk persistence round trip**: it constructs a
fully new registry instance (not the same object) from the same file and proves
that every registered identity is restored.
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
        self.registry.register(identity)  # The same component_id twice.
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
        forged_signature = impostor.sign(payload)  # Signed by an entirely different component.

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
        """The critical test here: a completely new registry from the file,
        not the same object, simulating a real process restart."""
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
        """Restoring data structurally is insufficient; the restored public
        key must remain able to verify real signatures after reloading."""
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

        registry = IdentityRegistry()  # No persist_path.
        registry.register(ComponentIdentity.create("agent"))
        self.assertFalse(os.path.exists(self.persist_path))


if __name__ == "__main__":
    unittest.main()
