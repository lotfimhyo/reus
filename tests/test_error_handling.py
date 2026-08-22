"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

يثبت معالجات الأخطاء الشاملة في api/main.py (لم تكن مغطاة باختبار مخصَّص
سابقًا، فقط بفحص يدوي أثناء التطوير):
- كل استجابة، ناجحة أو فاشلة، تحمل X-Request-ID للربط بسجلات الخادم.
- خطأ تحقق (422) يُعاد بشكل موحَّد مع بقية الواجهة (`detail` نصي)، لا شكل
  Pydantic الافتراضي المختلف تمامًا.
- استثناء غير مُلتقَط صراحة في أي مسار لا يُسرِّب أي تفصيل داخلي في
  الاستجابة، لكنه يُسجَّل خادميًا كاملًا مع نفس request_id للتشخيص.
"""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.main import app


class TestErrorEnvelope(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_every_response_carries_a_request_id_header(self):
        response = self.client.get("/health")
        self.assertIn("X-Request-ID", response.headers)
        # يجب أن يكون uuid4 صالحًا شكليًا، لا نصًا عشوائيًا
        import uuid

        uuid.UUID(response.headers["X-Request-ID"])

    def test_validation_error_returns_consistent_json_shape(self):
        import os

        os.environ["REUS_USER_API_KEY"] = "test-key"
        import config

        config.get_settings.cache_clear()

        try:
            # /chat يتطلب حقل prompt؛ إرسال جسم فارغ (بمفتاح صحيح، حتى يصل
            # الطلب فعليًا لمرحلة تحقق الجسم) يُفجِّر تحقق Pydantic (422)
            response = self.client.post("/chat", json={}, headers={"x-api-key": "test-key"})
            self.assertEqual(response.status_code, 422)
            body = response.json()
            self.assertIn("detail", body)
            self.assertIsInstance(body["detail"], str)
            self.assertIn("errors", body)
            self.assertIn("request_id", body)
        finally:
            os.environ.pop("REUS_USER_API_KEY", None)
            config.get_settings.cache_clear()

    def test_unhandled_exception_returns_generic_message_not_internal_details(self):
        from container import get_task_executor

        class ExplodingExecutor:
            def execute(self, task):
                raise RuntimeError("internal database connection string: postgresql://secret")

        import os

        os.environ["REUS_USER_API_KEY"] = "test-key"
        import config

        config.get_settings.cache_clear()

        app.dependency_overrides[get_task_executor] = lambda: ExplodingExecutor()
        try:
            response = self.client.post(
                "/chat", json={"prompt": "hi"}, headers={"x-api-key": "test-key"}
            )
            self.assertEqual(response.status_code, 500)
            body = response.json()
            self.assertNotIn("postgresql://secret", response.text)
            self.assertNotIn("RuntimeError", response.text)
            self.assertIn("request_id", body)
        finally:
            app.dependency_overrides.pop(get_task_executor, None)
            os.environ.pop("REUS_USER_API_KEY", None)
            config.get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
