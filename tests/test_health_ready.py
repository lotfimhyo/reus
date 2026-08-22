"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

يثبت: /health يبقى فحصًا رخيصًا لا يفحص أي تبعية (Liveness)، بينما /ready
يفحص فعليًا التبعيات المُفعَّلة (Readiness) ويُعيد 503 صريح عند تعذّر الوصول
لأي منها بدل الإعلان الكاذب عن الجهوزية.
"""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.main import app


class TestHealthAndReady(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_is_always_ok_and_cheap(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_ready_reports_ok_when_backends_are_memory(self):
        """الإعداد الافتراضي في بيئة الاختبار: storage_backend=memory,
        event_bus_backend=memory — لا تبعيات خارجية فعلية لفحصها، فيجب أن
        يُعلَن الجهوزية فورًا مع توضيح أن الفحوصات تم تخطيها لا أنها نجحت وهميًا."""
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        self.assertIn("skipped", body["checks"]["database"])
        self.assertIn("skipped", body["checks"]["redis"])

    def test_ready_returns_503_when_configured_postgres_is_unreachable(self):
        """يحاكي هذا الاختبار عمدًا تغيير REUS_DATABASE_URL في نفس العملية —
        وهو ما لا يحدث في الإنتاج (يُضبَط مرة واحدة عند الإقلاع) لكنه كشف
        فعليًا أن get_engine()/get_session_factory() في infrastructure/
        postgres/session.py مُخزَّنتان (`@lru_cache`) بشكل مستقل تمامًا عن
        get_settings() — إن لم تُفرَّغا صراحة هنا، يبقى محرك قاعدة بيانات
        معطوب مخزَّنًا طوال عمر العملية، فيُفسد أي اختبار Postgres حقيقي
        آخر يُشغَّل لاحقًا في نفس الجلسة. هذا اكتُشِف بالتشغيل الفعلي، لا
        نظريًا: كان هذا الاختبار بالذات يُفشل 19 اختبارًا في
        tests/test_postgres_repositories.py عند تشغيل المجموعة كاملة، رغم
        نجاحها جميعًا حين تُشغَّل وحدها."""
        import os

        import config
        from config import Settings
        from infrastructure.postgres import session as postgres_session

        broken_settings = Settings(
            storage_backend="postgres",
            database_url="postgresql+psycopg://nouser:nopass@localhost:1/nonexistent_db_for_test",
        )
        app.dependency_overrides.clear()

        try:
            os.environ["REUS_STORAGE_BACKEND"] = "postgres"
            os.environ["REUS_DATABASE_URL"] = broken_settings.database_url
            config.get_settings.cache_clear()
            postgres_session.get_engine.cache_clear()
            postgres_session.get_session_factory.cache_clear()

            response = self.client.get("/ready")
            self.assertEqual(response.status_code, 503)
            body = response.json()["detail"]
            self.assertEqual(body["status"], "not_ready")
            self.assertIn("unreachable", body["checks"]["database"])
        finally:
            os.environ.pop("REUS_STORAGE_BACKEND", None)
            os.environ.pop("REUS_DATABASE_URL", None)
            config.get_settings.cache_clear()
            # حرِج: بدون هذا يبقى المحرك المعطوب أعلاه مخزَّنًا لبقية
            # الجلسة رغم إعادة الإعدادات — انظر شرح سبب الاختبار أعلاه.
            postgres_session.get_engine.cache_clear()
            postgres_session.get_session_factory.cache_clear()


if __name__ == "__main__":
    unittest.main()
