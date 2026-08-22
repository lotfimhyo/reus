"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

يثبت الحلقة الكاملة المطلوبة صراحةً: "العقد تطور نفسها عبر اشراف بشري في
تلقرام". الشيء الوحيد المُحاكى هنا هو استجابة خادم Ollama نفسه (عبر حقن
`OllamaClient` وهمي بدل استدعاء HTTP حقيقي لخادم Ollama غير متوفر في بيئة
هذا الاختبار) — كل شيء آخر حقيقي فعليًا: `static_analyze`، `AgentSandbox`
(subprocess معزول حقيقي)، `CapabilityLayer.publish`، `LocalExecutor`، وبوابة
موافقة `TelegramService` الحقيقية بخطوتيها (`/approve_capability` ثم
`/approve`).

Run: `python3 -m unittest tests.test_capability_evolution -v`
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from application.agent_token_service import AgentTokenService
from application.capability_evolution_service import CapabilityEvolutionService
from application.orchestrator_service import OrchestratorService
from application.telegram_service import TelegramService
from infrastructure.agent_factory.builder import AgentBuilder
from infrastructure.agent_factory.independent_test_reviewer import IndependentTestReviewer
from infrastructure.agent_factory.manifest import AgentSpec, TestCase
from infrastructure.agent_factory.ollama_synthesizer import OllamaSynthesizer
from infrastructure.agent_token_repository import InMemoryAgentTokenRepository
from infrastructure.capability_binder import AgentCapabilityBinder
from infrastructure.cognitive_core.capability.capability_layer import CapabilityLayer
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.node_roles import NODE_ROLES
from infrastructure.pending_capabilities import PendingCapabilityStore
from infrastructure.telegram_link_repository import InMemoryTelegramLinkRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository


class _FakeOllamaClient:
    """يحاكي استجابة خادم Ollama نفسه فقط (لا شيء أبعد من ذلك) — يعيد نص
    منطق `run()` صالحًا لمهارة 'عكس الكلمات في جملة'، ثم لاحقًا حالات
    اختبار إضافية بصيغة JSON، تمامًا كما يفعل خادم Ollama حقيقي."""

    def __init__(self):
        self.calls: list[str] = []

    def generate(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        self.calls.append(prompt)
        if json_mode:
            # استجابة IndependentTestReviewer: حالة اختبار إضافية مستقلة
            return '[{"input": "one two", "expected_output": "two one"}]'
        # استجابة OllamaSynthesizer: جسم دالة run() فقط
        return "return ' '.join(str(input_data).split()[::-1])"


class TestCapabilityEvolution(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp_root = Path(self._tmp.name)

        self.audit_log = AppendOnlyAuditLog(str(tmp_root / "audit.jsonl"))
        self.capabilities = CapabilityLayer(self.audit_log, data_dir=str(tmp_root / "capabilities"))
        self.executor = LocalExecutor()

        self.fake_ollama = _FakeOllamaClient()
        synthesizer = OllamaSynthesizer(self.fake_ollama)
        reviewer = IndependentTestReviewer(self.fake_ollama)
        agent_builder = AgentBuilder(
            output_dir=str(tmp_root / "agents"), synthesizer=synthesizer, test_reviewer=reviewer
        )
        self.binder = AgentCapabilityBinder(
            builder=agent_builder, capability_layer=self.capabilities, local_executor=self.executor
        )

        self.pending_store = PendingCapabilityStore()
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

        self.evolution = CapabilityEvolutionService(
            binder=self.binder,
            pending_store=self.pending_store,
            telegram=self.telegram,
            admin_chat_ids=frozenset({self.admin_chat_id}),
            event_bus=event_bus,
        )

        self._original_text_specs = list(NODE_ROLES["text-node"].specs)

    def tearDown(self):
        NODE_ROLES["text-node"].specs[:] = self._original_text_specs
        self._tmp.cleanup()

    def test_proposed_capability_is_not_executable_before_human_approval(self):
        spec = AgentSpec(
            name="word_reverser",
            capability="text.reverse_words",
            description="يعكس ترتيب الكلمات في جملة",
            template="ollama-generated",
            test_cases=[TestCase(input="hello world", expected_output="world hello")],
        )

        result = self.evolution.propose_capability("text-node", spec)
        self.assertTrue(result.approved, result.reason)

        # نموذج Ollama استُدعي مرتين حقيقيتين: كتابة المنطق + مراجعة مستقلة.
        self.assertEqual(len(self.fake_ollama.calls), 2)

        pending = self.pending_store.list_pending()
        self.assertEqual(len(pending), 1)

        # لم تُربَط القدرة بعد — لا يمكن تنفيذها، ولا أُضيفت لمهارات العقدة.
        self.assertFalse(self.capabilities.find_by_name("text.reverse_words"))
        self.assertNotIn("text.reverse_words", [s.capability for s in NODE_ROLES["text-node"].specs])

        # إشعار حقيقي وصل لمحادثة الإدارة.
        self.assertTrue(any("text.reverse_words" in text for _, text in self.sent_messages))

    def test_human_approval_via_telegram_binds_capability_and_evolves_node_role(self):
        spec = AgentSpec(
            name="word_reverser",
            capability="text.reverse_words",
            description="يعكس ترتيب الكلمات في جملة",
            template="ollama-generated",
            test_cases=[TestCase(input="hello world", expected_output="world hello")],
        )
        self.evolution.propose_capability("text-node", spec)
        request_id = self.pending_store.list_pending()[0].request_id

        reply1 = self.telegram.handle_incoming_message(self.admin_chat_id, f"/approve_capability {request_id}")
        self.assertEqual(reply1, "✅")

        approval_text = next(text for _, text in self.sent_messages if text.startswith("⚠️"))
        approval_id = approval_text.split("[")[1].split("]")[0]
        reply2 = self.telegram.handle_incoming_message(self.admin_chat_id, f"/approve {approval_id}")
        self.assertEqual(reply2, "✅")

        # الآن: القدرة مربوطة فعليًا، وقابلة للتنفيذ الحقيقي عبر LocalExecutor.
        descriptors = self.capabilities.find_by_name("text.reverse_words")
        self.assertEqual(len(descriptors), 1)
        capability_id = descriptors[0].capability_id
        self.assertTrue(self.executor.is_registered(capability_id))

        class _Step:
            pass

        step = _Step()
        step.capability_id = capability_id
        outcome = self.executor(step, {"input": "one two three"})
        self.assertTrue(outcome.success, outcome.error)
        self.assertEqual(outcome.output, "three two one")

        # العقدة "تطوّرت لنفسها": مهاراتها الآن تتضمن القدرة الجديدة.
        self.assertIn("text.reverse_words", [s.capability for s in NODE_ROLES["text-node"].specs])


if __name__ == "__main__":
    unittest.main()
