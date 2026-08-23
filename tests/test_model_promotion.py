"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Run: `python3 -m unittest tests.test_model_promotion -v`
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from application.agent_token_service import AgentTokenService
from application.model_promotion_service import ModelPromotionService
from application.ollama_task_executor import OllamaTaskExecutor
from application.orchestrator_service import OrchestratorService
from application.telegram_service import TelegramService
from infrastructure.agent_factory.builder import AgentBuilder
from infrastructure.agent_token_repository import InMemoryAgentTokenRepository
from infrastructure.capability_binder import AgentCapabilityBinder
from infrastructure.cognitive_core.capability.capability_layer import CapabilityLayer
from infrastructure.cognitive_core.cognitive.engine import CognitiveEngine
from infrastructure.cognitive_core.cognitive.goal import Goal
from infrastructure.cognitive_core.cognitive.learning import LearningLayer
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog
from infrastructure.cognitive_core.memory.memory_layer import MemoryLayer
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.model_promotion import ActiveModelStore
from infrastructure.model_training.local_model_builder import LocalModelBuilder
from infrastructure.model_training.training_dataset import TrainingDatasetStore
from infrastructure.node_roles import NODE_ROLES
from infrastructure.telegram_link_repository import InMemoryTelegramLinkRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository


class _FakeOllamaClient:
    def __init__(self):
        self.model = "llama3.1"
        self.calls: list = []

    def generate(self, prompt, system=None, json_mode=False, model=None):
        self.calls.append((prompt, model))
        return f"echo:{prompt}"


class TestModelPromotion(unittest.TestCase):
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

        uppercase_spec = next(s for s in NODE_ROLES["text-node"].specs if s.capability == "text.uppercase")
        self.binder.build_and_bind(uppercase_spec)

        self.dataset = TrainingDatasetStore(tmp_root / "training" / "dataset.jsonl")

        self.build_calls = []

        class _FakeCompletedProcess:
            returncode = 0
            stdout = "ok"
            stderr = ""

        def fake_runner(args):
            self.build_calls.append(args)
            return _FakeCompletedProcess()

        self.model_builder = LocalModelBuilder(
            dataset=self.dataset,
            learning=self.learning,
            command_runner=fake_runner,
            model_name="reus-evolved-test",
            workdir=str(tmp_root / "model_training"),
        )

        self.active_model_store = ActiveModelStore(tmp_root / "active_model.json", base_model="llama3.1")

        self.admin_chat_id = "admin-chat-1"
        self.sent_messages: list = []
        event_bus = InMemoryEventBus()
        agent_repo = InMemoryAgentRepository()
        token_service = AgentTokenService(token_repo=InMemoryAgentTokenRepository(), agent_repo=agent_repo)
        orchestrator = OrchestratorService(
            workflow_repo=InMemoryWorkflowRepository(), agent_repo=agent_repo, event_bus=event_bus
        )
        self.telegram = TelegramService(
            link_repo=InMemoryTelegramLinkRepository(),
            token_service=token_service,
            orchestrator=orchestrator,
            event_bus=event_bus,
            admin_chat_ids=frozenset({self.admin_chat_id}),
        )
        self.telegram.set_delivery_callback(lambda chat_id, text: self.sent_messages.append((chat_id, text)))
        self.telegram.start()

        self.promotion = ModelPromotionService(
            dataset=self.dataset,
            learning=self.learning,
            model_builder=self.model_builder,
            active_model_store=self.active_model_store,
            telegram=self.telegram,
            admin_chat_ids=frozenset({self.admin_chat_id}),
            evolved_model_name="reus-evolved-test",
            min_examples=3,
            event_bus=event_bus,
        )

        self.fake_ollama_client = _FakeOllamaClient()
        self.task_executor = OllamaTaskExecutor(
            client=self.fake_ollama_client, active_model_store=self.active_model_store
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _run_real_goal(self, text: str) -> None:
        goal = Goal(description="uppercase", payload={"input": text}, required_capability_name="text.uppercase")
        self.engine.run(goal, self.executor)

    def test_not_ready_before_enough_examples(self):
        self._run_real_goal("a")
        self.dataset.harvest(self.memory)
        report = self.promotion.evaluate_readiness()
        self.assertFalse(report.ready)
        self.assertIn("below the minimum", report.reason())

    def test_full_maturity_to_promotion_flow_and_executor_uses_new_model_immediately(self):
        for text in ["a", "b", "c"]:
            self._run_real_goal(text)
        self.dataset.harvest(self.memory)
        self.model_builder.build()

        report = self.promotion.evaluate_readiness()
        self.assertTrue(report.ready, report.reason())

        from domain.workflow import TaskNode

        result_before = self.task_executor.execute(TaskNode(name="t", payload={"prompt": "hi"}))
        self.assertEqual(result_before["model_used"], "llama3.1")

        self.promotion.notify_if_newly_ready()
        self.assertTrue(any("meets the configured maturity criteria" in text for _, text in self.sent_messages))

        reply1 = self.telegram.handle_incoming_message(self.admin_chat_id, "/promote_model")
        self.assertEqual(reply1, "✅")
        approval_text = next(text for _, text in self.sent_messages if text.startswith("⚠️"))
        approval_id = approval_text.split("[")[1].split("]")[0]
        reply2 = self.telegram.handle_incoming_message(self.admin_chat_id, f"/approve {approval_id}")
        self.assertEqual(reply2, "✅")

        self.assertEqual(self.active_model_store.get_active(), "reus-evolved-test")
        self.assertTrue(self.active_model_store.is_promoted())

        result_after = self.task_executor.execute(TaskNode(name="t2", payload={"prompt": "hi again"}))
        self.assertEqual(result_after["model_used"], "reus-evolved-test")
        self.assertEqual(self.fake_ollama_client.calls[-1], ("hi again", "reus-evolved-test"))

    def test_demote_reverts_to_base_model_without_readiness_check(self):
        self.active_model_store.set_active("reus-evolved-test")
        reply = self.telegram.handle_incoming_message(self.admin_chat_id, "/demote_model")
        self.assertEqual(reply, "✅")
        self.assertEqual(self.active_model_store.get_active(), "llama3.1")
        self.assertFalse(self.active_model_store.is_promoted())

    def test_promote_command_refuses_when_not_ready(self):
        reply = self.telegram.handle_incoming_message(self.admin_chat_id, "/promote_model")
        self.assertEqual(reply, "✅")
        self.assertTrue(any("not ready for promotion" in text for _, text in self.sent_messages))
        self.assertFalse(self.active_model_store.is_promoted())


if __name__ == "__main__":
    unittest.main()
