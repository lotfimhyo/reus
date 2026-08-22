"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

يثبت إصلاح فجوة حقيقية أبلغ عنها المؤسس: لم توجد أي طريقة عبر لوحة
التحكم للحصول على رمز وكيل صالح لربط تلغرام. يثبت هذا الملف: زر توليد
الرمز موجود فعليًا في HTML الناتج، بالنمط الآمن (تفويض حدث + data-agent-id
لا onclick مبني بسلسلة نصية)، ورسالة رفض /link أصبحت تشرح الحل الفعلي.
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
        self.assertIn("توليد رمز لتلغرام", reply)


if __name__ == "__main__":
    unittest.main()
