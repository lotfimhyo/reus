"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Requires FastAPI and Pydantic, which are declared project dependencies in
requirements.txt. Run it in an environment where those dependencies are
installed:
`python3 -m unittest tests.test_chat_endpoint -v`

Verifies credential separation between /chat and administrative routes: a
user key must not work on /workflows and an administrative key must not work
on /chat. It also verifies ChatResponse normalization across result shapes and
that TaskExecutionError maps to a clear 502 response rather than an opaque
failure.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from api.schemas_chat import ChatResponse
from application.task_executor import TaskExecutionError, TaskExecutor
from container import get_task_executor
from domain.workflow import TaskNode


class _FakeTaskExecutor(TaskExecutor):
    def __init__(self, result=None, error: str | None = None):
        self._result = result
        self._error = error
        self.received_tasks: list[TaskNode] = []

    def execute(self, task: TaskNode):
        self.received_tasks.append(task)
        if self._error:
            raise TaskExecutionError(self._error)
        return self._result


class TestChatResponseNormalization(unittest.TestCase):
    def test_normalizes_ollama_style_dict_result(self):
        result = {"model_used": "llama3.1", "provider": "ollama", "response": "مرحبًا"}
        chat_response = ChatResponse.from_executor_result(result)
        self.assertEqual(chat_response.response, "مرحبًا")
        self.assertEqual(chat_response.provider, "ollama")
        self.assertEqual(chat_response.model_used, "llama3.1")
        self.assertIsNone(chat_response.fallback_from)

    def test_includes_fallback_from_when_present(self):
        result = {"response": "رد احتياطي", "provider": "anthropic", "fallback_from": "ollama"}
        chat_response = ChatResponse.from_executor_result(result)
        self.assertEqual(chat_response.fallback_from, "ollama")

    def test_normalizes_plain_non_dict_result_from_other_executor_modes(self):
        chat_response = ChatResponse.from_executor_result(42)
        self.assertEqual(chat_response.response, "42")
        self.assertIsNone(chat_response.provider)


class TestChatEndpoint(unittest.TestCase):
    def setUp(self):
        self._environment = patch.dict(
            os.environ,
            {
                "REUS_API_KEY": "admin-test-key-at-least-24-characters",
                "REUS_USER_API_KEY": "user-test-key-at-least-24-characters",
            },
        )
        self._environment.start()
        from config import get_settings

        get_settings.cache_clear()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self._environment.stop()
        from config import get_settings

        get_settings.cache_clear()

    def test_missing_api_key_is_rejected(self):
        response = self.client.post("/chat", json={"prompt": "hi"})
        self.assertEqual(response.status_code, 401)

    def test_admin_api_key_does_not_grant_access_to_chat(self):
        """Credential separation: user_api_key is distinct from the administrative api_key."""
        from config import get_settings

        settings = get_settings()
        response = self.client.post(
            "/chat", json={"prompt": "hi"}, headers={"X-API-Key": settings.api_key}
        )
        self.assertEqual(response.status_code, 401)

    def test_successful_chat_returns_normalized_response(self):
        fake_executor = _FakeTaskExecutor(
            result={"model_used": "llama3.1", "provider": "ollama", "response": "أهلًا بك"}
        )
        app.dependency_overrides[get_task_executor] = lambda: fake_executor

        from config import get_settings

        response = self.client.post(
            "/chat",
            json={"prompt": "مرحبًا"},
            headers={"X-API-Key": get_settings().user_api_key},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["response"], "أهلًا بك")
        self.assertEqual(body["provider"], "ollama")
        self.assertEqual(fake_executor.received_tasks[0].payload["prompt"], "مرحبًا")

    def test_task_execution_error_maps_to_502(self):
        fake_executor = _FakeTaskExecutor(error="تعذّر الوصول للنموذج")
        app.dependency_overrides[get_task_executor] = lambda: fake_executor

        from config import get_settings

        response = self.client.post(
            "/chat", json={"prompt": "hi"}, headers={"X-API-Key": get_settings().user_api_key}
        )
        self.assertEqual(response.status_code, 502)

    def test_stream_emits_real_lifecycle_events(self):
        fake_executor = _FakeTaskExecutor(result={"response": "نتيجة", "provider": "ollama"})
        app.dependency_overrides[get_task_executor] = lambda: fake_executor

        from config import get_settings

        response = self.client.post(
            "/chat/stream", json={"prompt": "مرحبًا"}, headers={"X-API-Key": get_settings().user_api_key}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("event: accepted", response.text)
        self.assertIn("event: answer", response.text)
        self.assertIn("نتيجة", response.text)


if __name__ == "__main__":
    unittest.main()
