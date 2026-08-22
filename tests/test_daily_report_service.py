"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Run: `python3 -m unittest tests.test_daily_report_service -v`
"""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from application.agent_token_service import AgentTokenService
from application.daily_report_service import DailyReportService
from application.orchestrator_service import OrchestratorService
from application.telegram_service import TelegramService
from infrastructure.agent_factory.builder import AgentBuilder
from infrastructure.agent_token_repository import InMemoryAgentTokenRepository
from infrastructure.autonomy.ledger import InMemoryGovernanceLedger
from infrastructure.capability_binder import AgentCapabilityBinder
from infrastructure.cognitive_core.capability.capability_layer import CapabilityLayer
from infrastructure.cognitive_core.cognitive.engine import CognitiveEngine
from infrastructure.cognitive_core.cognitive.goal import Goal
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog
from infrastructure.cognitive_core.memory.memory_layer import MemoryLayer
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.model_training.local_model_builder import LocalModelBuilder
from infrastructure.model_training.training_dataset import TrainingDatasetStore
from infrastructure.node_roles import NODE_ROLES
from infrastructure.telegram_link_repository import InMemoryTelegramLinkRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository


class TestDailyReportService(unittest.TestCase):
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
        self.engine = CognitiveEngine(self.memory, self.capabilities, self.audit_log)

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
            learning=None,
            command_runner=fake_runner,
            model_name="reus-evolved-test",
            workdir=str(tmp_root / "model_training"),
        )

        self.admin_chat_id = "admin-chat-1"
        self.sent_messages: list[tuple[str, str]] = []
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

        self.service = DailyReportService(
            memory=self.memory,
            dataset=self.dataset,
            model_builder=self.model_builder,
            telegram=self.telegram,
            admin_chat_ids=frozenset({self.admin_chat_id}),
            interval_seconds=9999.0,
            governance=InMemoryGovernanceLedger(),
        )

    def tearDown(self):
        self.service.stop()
        self._tmp.cleanup()

    def _run_real_goal(self, text: str) -> None:
        goal = Goal(description="uppercase", payload={"input": text}, required_capability_name="text.uppercase")
        self.engine.run(goal, self.executor)

    def test_run_once_harvests_builds_model_and_sends_real_report(self):
        self._run_real_goal("abc")
        self._run_real_goal("def")

        summary = self.service.run_once()

        self.assertEqual(summary.newly_harvested, 2)
        self.assertEqual(summary.total_examples, 2)
        self.assertEqual(summary.proposal_counts, {})
        self.assertIsNotNone(summary.model_build)
        self.assertTrue(summary.model_build.success)
        self.assertEqual(len(self.build_calls), 1)

        self.assertTrue(self.sent_messages)
        report_text = self.sent_messages[-1][1]
        self.assertIn("أمثلة تدريب جديدة اليوم: 2", report_text)
        self.assertIn("reus-evolved-test", report_text)

    def test_run_once_skips_model_build_when_nothing_new(self):
        summary = self.service.run_once()
        self.assertEqual(summary.newly_harvested, 0)
        self.assertIsNone(summary.model_build)
        self.assertEqual(len(self.build_calls), 0)  # لم يُستدعَ ollama create إطلاقًا

    def test_background_loop_stops_immediately_without_waiting_full_interval(self):
        self.service.start()
        time.sleep(0.2)  # يسمح للدورة الأولى (run_once) بالاكتمال
        start = time.monotonic()
        self.service.stop()
        elapsed = time.monotonic() - start
        # الفاصل الزمني 9999 ثانية — لولا threading.Event.wait القابل
        # للإيقاف الفوري، كان stop() سينتظر قرابة هذا الرقم كاملًا.
        self.assertLess(elapsed, 2.0)
        self.assertTrue(self.sent_messages)  # الدورة الأولى فعلًا أرسلت تقريرًا


if __name__ == "__main__":
    unittest.main()
