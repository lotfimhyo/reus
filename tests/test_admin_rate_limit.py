"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

يثبت الإصلاح الأمني الفعلي: المفتاح الإداري (REUS_API_KEY) — أقوى صلاحية
في النظام — كان بلا أي تحديد معدل رغم كونه على نفس السطح الشبكي العام
الذي يخدم /chat، بينما /chat محمي منذ الجلسة السابقة فقط. هذا يثبت أن
verify_api_key وrequire_agent_scope (المُطبَّقان مركزيًا في
infrastructure/security.py) يحدّان الآن من محاولات تخمين المفتاح الفاشلة
نفسها أيضًا، لا فقط الاستخدام بعد نجاح المصادقة — ويثبت أن هذا الحد مستقل
تمامًا عن حد /chat (مطاردة أحدهما لا تستهلك حصة الآخر).
"""
from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient


class TestAdminRateLimit(unittest.TestCase):
    def setUp(self):
        os.environ["REUS_API_KEY"] = "real-admin-key"
        os.environ["REUS_ADMIN_RATE_LIMIT_PER_MINUTE"] = "3"

        import config

        config.get_settings.cache_clear()

        import container

        container.get_admin_rate_limiter.cache_clear()

        from api.main import app

        self.client = TestClient(app)

    def tearDown(self):
        os.environ.pop("REUS_API_KEY", None)
        os.environ.pop("REUS_ADMIN_RATE_LIMIT_PER_MINUTE", None)

        import config

        config.get_settings.cache_clear()

        import container

        container.get_admin_rate_limiter.cache_clear()

    def test_admin_key_guessing_attempts_are_rate_limited(self):
        """الاختبار الأهم: محاولات تخمين مفتاح خاطئ (401) تُستهلَك من الحد
        نفسه — لا تُتاح بلا حدود لمجرد أنها فاشلة."""
        for _ in range(3):
            response = self.client.get("/agents/does-not-exist", headers={"x-api-key": "wrong-key"})
            self.assertEqual(response.status_code, 401)

        response = self.client.get("/agents/does-not-exist", headers={"x-api-key": "real-admin-key"})
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

    def test_correct_key_requests_within_limit_are_not_blocked(self):
        for _ in range(3):
            response = self.client.get("/agents/does-not-exist", headers={"x-api-key": "real-admin-key"})
            self.assertNotEqual(response.status_code, 429)

    def test_admin_rate_limit_is_independent_from_chat_rate_limit(self):
        """استهلاك حد /chat لا يجب أن يؤثر إطلاقًا على حد المسارات الإدارية،
        والعكس — دلائل حقيقية أن هذا محدِّد معدل منفصل، لا نفس الكائن بالخطأ."""
        os.environ["REUS_USER_API_KEY"] = "user-key"
        import config

        config.get_settings.cache_clear()
        try:
            for _ in range(3):
                self.client.get("/agents/does-not-exist", headers={"x-api-key": "wrong-key"})
            # حد الإدارة الآن مستهلَك بالكامل (3/3) — لكن /chat يجب أن يبقى يعمل
            response = self.client.post(
                "/chat", json={"prompt": "hi"}, headers={"x-api-key": "user-key"}
            )
            self.assertNotEqual(response.status_code, 429)
        finally:
            os.environ.pop("REUS_USER_API_KEY", None)
            config.get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
