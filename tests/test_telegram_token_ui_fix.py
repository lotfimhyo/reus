"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Proves a real gap reported by the founder: the dashboard had no way to obtain
a valid agent token for linking Telegram. This file proves that the token
generation button is present in the rendered HTML using the safe pattern
(event delegation plus data-agent-id, not a string-built onclick), and that the
/link rejection message now explains the actual remedy.
"""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient


class TestDashboardTelegramTokenUI(unittest.TestCase):
    def setUp(self):
        from api.main import app

        self.client = TestClient(app)

    def test_dashboard_has_the_issue_token_button(self):
        response = self.client.get("/dashboard")
        self.assertIn("issue-token-btn", response.text)
        self.assertIn("data-agent-id=", response.text)

    def test_dashboard_does_not_use_the_unsafe_inline_onclick_pattern(self):
        response = self.client.get("/dashboard")
        self.assertNotIn('onclick="issueTelegramToken(', response.text)


class TestTelegramLinkErrorMessage(unittest.TestCase):
    def test_invalid_token_message_points_to_the_dashboard(self):
        from container import get_telegram_service

        service = get_telegram_service()
        reply = service.handle_incoming_message("chat-1", "/link rvos_not-a-real-token")
        self.assertIn("dashboard", reply)
        self.assertIn("generate a Telegram token", reply)


if __name__ == "__main__":
    unittest.main()
