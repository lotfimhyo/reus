"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Regression test for a real gap found via live end-to-end testing (not unit
tests, which always mock the executor): a fresh deployment with no extra
configuration uses REUS_TASK_EXECUTOR="default" (DefaultTaskExecutor),
which requires a pre-registered agent_id per task -- but /chat never sets
one (it's a stateless, agent-less endpoint by design). Every /chat request
against an unconfigured deployment returned 502 with a message that gave
no indication of the actual fix. This test proves the message now names
the real cause and the concrete settings that resolve it.
"""
from __future__ import annotations

import unittest

from application.agent_service import AgentService
from application.memory_service import MemoryService
from domain.workflow import TaskNode
from infrastructure.default_task_executor import DefaultTaskExecutor


class TestDefaultTaskExecutorChatErrorMessage(unittest.TestCase):
    def setUp(self):
        self.executor = DefaultTaskExecutor(
            agent_service=AgentService.__new__(AgentService),
            memory_service=MemoryService.__new__(MemoryService),
        )

    def test_chat_shaped_task_without_agent_gets_an_actionable_message(self):
        task = TaskNode(name="web_chat", payload={"prompt": "hello", "system": None})

        with self.assertRaises(Exception) as ctx:
            self.executor.execute(task)

        message = str(ctx.exception)
        self.assertIn("REUS_TASK_EXECUTOR", message)
        self.assertIn("ollama", message)
        self.assertIn("model_router", message)

    def test_non_chat_task_without_agent_keeps_the_original_generic_message(self):
        task = TaskNode(name="structured_task", payload={"some_field": "value"})

        with self.assertRaises(Exception) as ctx:
            self.executor.execute(task)

        message = str(ctx.exception)
        self.assertIn("has no assigned agent", message)
        self.assertNotIn("REUS_TASK_EXECUTOR", message)


if __name__ == "__main__":
    unittest.main()
