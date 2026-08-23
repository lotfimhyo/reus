"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Verifies that training-data harvesting comes from local execution rather than
synthetic fixtures: it builds a text node through ``AgentCapabilityBinder``,
runs multiple goals through ``CognitiveEngine.run()``, harvests successful
episodes into ``TrainingDatasetStore``, and builds Modelfile content. The
``ollama create`` subprocess is injected because Ollama is not installed in
this environment, so the test verifies command construction only. It does not
run Ollama or claim weight fine-tuning.

Run: `python3 -m unittest tests.test_model_training -v`
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from infrastructure.agent_factory.builder import AgentBuilder
from infrastructure.capability_binder import AgentCapabilityBinder
from infrastructure.cognitive_core.capability.capability_layer import CapabilityLayer
from infrastructure.cognitive_core.cognitive.engine import CognitiveEngine
from infrastructure.cognitive_core.cognitive.goal import Goal
from infrastructure.cognitive_core.cognitive.learning import LearningLayer
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog
from infrastructure.cognitive_core.memory.memory_layer import MemoryLayer
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.model_training.local_model_builder import LocalModelBuilder, ModelfileBuilder
from infrastructure.model_training.training_dataset import TrainingDatasetStore
from infrastructure.node_roles import NODE_ROLES


class TestModelTraining(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp_root = Path(self._tmp.name)

        self.audit_log = AppendOnlyAuditLog(str(tmp_root / "audit.jsonl"))
        self.capabilities = CapabilityLayer(self.audit_log, data_dir=str(tmp_root / "capabilities"))
        self.memory = MemoryLayer(self.audit_log, data_dir=str(tmp_root / "memory"))
        self.executor = LocalExecutor()
        self.builder = AgentBuilder(output_dir=str(tmp_root / "agents"))
        self.binder = AgentCapabilityBinder(
            builder=self.builder, capability_layer=self.capabilities, local_executor=self.executor
        )
        self.learning = LearningLayer(self.memory, self.audit_log)
        self.engine = CognitiveEngine(self.memory, self.capabilities, self.audit_log, learning=self.learning)

        # Build one real text capability from the five node roles and execute it repeatedly.
        text_role = NODE_ROLES["text-node"]
        uppercase_spec = next(s for s in text_role.specs if s.capability == "text.uppercase")
        self.binder.build_and_bind(uppercase_spec)

        self.dataset_path = tmp_root / "training" / "dataset.jsonl"
        self.dataset = TrainingDatasetStore(self.dataset_path)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_real_goal(self, text: str) -> None:
        goal = Goal(description="uppercase test", payload={"input": text}, required_capability_name="text.uppercase")
        self.engine.run(goal, self.executor)

    def test_harvest_only_pulls_real_successful_episodes(self):
        self._run_real_goal("hello")
        self._run_real_goal("world")

        added = self.dataset.harvest(self.memory)
        self.assertEqual(added, 2)
        self.assertEqual(self.dataset.count(), 2)

        # An immediate second harvest is idempotent; no new episodes exist.
        added_again = self.dataset.harvest(self.memory)
        self.assertEqual(added_again, 0)
        self.assertEqual(self.dataset.count(), 2)

        examples = self.dataset.read_all()
        outputs = {e.output for e in examples}
        self.assertIn("HELLO", outputs)
        self.assertIn("WORLD", outputs)

    def test_modelfile_builder_produces_valid_content_from_real_examples(self):
        self._run_real_goal("abc")
        self.dataset.harvest(self.memory)
        examples_by_capability = self.dataset.examples_by_capability()

        content = ModelfileBuilder(base_model="llama3.1").build(examples_by_capability, ["text.uppercase: موثوق"])
        self.assertIn("FROM llama3.1", content)
        self.assertIn("SYSTEM", content)
        self.assertIn("text.uppercase", content)
        self.assertIn("'ABC'", content)

    def test_local_model_builder_invokes_ollama_create_with_correct_args(self):
        self._run_real_goal("xyz")
        self.dataset.harvest(self.memory)

        captured_args = {}

        class _FakeCompletedProcess:
            returncode = 0
            stdout = "success"
            stderr = ""

        def fake_runner(args):
            captured_args["args"] = args
            return _FakeCompletedProcess()

        model_builder = LocalModelBuilder(
            dataset=self.dataset,
            learning=self.learning,
            command_runner=fake_runner,
            model_name="reus-evolved-test",
            workdir=str(Path(self._tmp.name) / "model_training"),
        )
        result = model_builder.build()

        self.assertTrue(result.success)
        self.assertEqual(result.examples_used, 1)
        self.assertEqual(
            captured_args["args"],
            ["ollama", "create", "reus-evolved-test", "-f", result.modelfile_path],
        )
        self.assertTrue(Path(result.modelfile_path).exists())

    def test_local_model_builder_refuses_to_build_with_zero_examples(self):
        model_builder = LocalModelBuilder(
            dataset=self.dataset,  # Intentionally empty; no harvest was called.
            learning=None,
            command_runner=lambda args: (_ for _ in ()).throw(AssertionError("must not call ollama with 0 examples")),
            workdir=str(Path(self._tmp.name) / "model_training_empty"),
        )
        result = model_builder.build()
        self.assertFalse(result.success)
        self.assertEqual(result.examples_used, 0)


if __name__ == "__main__":
    unittest.main()
