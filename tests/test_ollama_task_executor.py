"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

يحقن عميل Ollama وهميًا فقط (لعدم توفر خادم Ollama حقيقي في بيئة الاختبار
هذه — نفس قيد باقي هذا المشروع)؛ كل شيء آخر — منطق السقوط التلقائي، نشر
الحدث، التمييز بين فشل بلا سقوط وفشل مع سقوط، ودمج بيانات السقوط في النتيجة
— حقيقي فعليًا ومُختبَر مباشرة.

Run: `python3 -m unittest tests.test_ollama_task_executor -v`
"""
from __future__ import annotations

import unittest

from application.ollama_task_executor import OllamaTaskExecutor
from application.task_executor import TaskExecutionError, TaskExecutor
from domain.workflow import TaskNode
from infrastructure.agent_factory.support.ollama_client import OllamaError
from infrastructure.event_bus import InMemoryEventBus


class _FakeOllamaClient:
    model = "llama3.1"

    def __init__(self, should_fail: bool = False, response: str = "fake response"):
        self.should_fail = should_fail
        self.response = response
        self.calls: list = []

    def generate(self, prompt: str, system=None, json_mode: bool = False, model=None) -> str:
        self.calls.append((prompt, system, json_mode, model))
        if self.should_fail:
            raise OllamaError("تعذّر الوصول للخادم المحلي (محاكى للاختبار)")
        return self.response


class _FakeFallbackExecutor(TaskExecutor):
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.executed_tasks: list = []

    def execute(self, task: TaskNode):
        self.executed_tasks.append(task)
        if self.should_fail:
            raise TaskExecutionError("منفّذ السقوط فشل أيضًا (محاكى للاختبار)")
        return {"model_used": "claude-sonnet-5", "provider": "anthropic", "response": "fallback response"}


class TestOllamaTaskExecutor(unittest.TestCase):
    def test_successful_ollama_call_returns_directly_without_fallback(self):
        client = _FakeOllamaClient(should_fail=False, response="مرحبًا")
        fallback = _FakeFallbackExecutor()
        executor = OllamaTaskExecutor(client=client, fallback_executor=fallback)

        task = TaskNode(name="t1", payload={"prompt": "قل مرحبًا"})
        result = executor.execute(task)

        self.assertEqual(result, {"model_used": "llama3.1", "provider": "ollama", "response": "مرحبًا"})
        self.assertEqual(len(fallback.executed_tasks), 0)  # لم يُستدعَ السقوط إطلاقًا

    def test_missing_prompt_raises_without_touching_ollama_or_fallback(self):
        client = _FakeOllamaClient()
        fallback = _FakeFallbackExecutor()
        executor = OllamaTaskExecutor(client=client, fallback_executor=fallback)

        task = TaskNode(name="t2", payload={})
        with self.assertRaises(TaskExecutionError):
            executor.execute(task)
        self.assertEqual(len(client.calls), 0)
        self.assertEqual(len(fallback.executed_tasks), 0)

    def test_ollama_failure_falls_back_automatically_and_publishes_event(self):
        client = _FakeOllamaClient(should_fail=True)
        fallback = _FakeFallbackExecutor(should_fail=False)
        bus = InMemoryEventBus()
        published: list = []
        bus.subscribe("task.ollama_fallback_used", lambda e: published.append((e.name, e.payload)))

        executor = OllamaTaskExecutor(client=client, fallback_executor=fallback, event_bus=bus)
        task = TaskNode(name="t3", payload={"prompt": "hello"})
        result = executor.execute(task)

        self.assertEqual(result["provider"], "anthropic")
        self.assertEqual(result["fallback_from"], "ollama")
        self.assertEqual(len(fallback.executed_tasks), 1)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0][1]["task_name"], "t3")

    def test_ollama_failure_without_fallback_configured_raises(self):
        client = _FakeOllamaClient(should_fail=True)
        executor = OllamaTaskExecutor(client=client, fallback_executor=None)
        task = TaskNode(name="t4", payload={"prompt": "hello"})
        with self.assertRaises(TaskExecutionError):
            executor.execute(task)

    def test_ollama_failure_and_fallback_failure_both_raise_combined_error(self):
        client = _FakeOllamaClient(should_fail=True)
        fallback = _FakeFallbackExecutor(should_fail=True)
        executor = OllamaTaskExecutor(client=client, fallback_executor=fallback)
        task = TaskNode(name="t5", payload={"prompt": "hello"})
        with self.assertRaises(TaskExecutionError) as ctx:
            executor.execute(task)
        self.assertIn("fallback executor also failed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
