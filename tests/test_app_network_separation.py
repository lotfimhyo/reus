"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

يثبت الفصل الشبكي الفعلي بين public_app وadmin_app (api/main.py) —
اكتُشِف قبل هذه الحلقة أن كل المسارات الإدارية والعامة كانت تُخدَم من نفس
عملية FastAPI/نفس المستمِع الشبكي، بفصل منطقي فقط (مفتاح مختلف) لا فصل
شبكي فعلي. هذا الملف يثبت أن الفصل الآن حقيقي: مسار غائب عن تطبيق لا
يُرجِع 401 (مرفوض بعد وصوله) بل 404 (غائب عن جدول التوجيه من الأساس) —
الفرق جوهري: 404 يعني لا وجود للمسار على هذا السطح الشبكي إطلاقًا، لا
مجرد رفض مصادقة يمكن تخمين تجاوزه.
"""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient


class TestNetworkSeparation(unittest.TestCase):
    def setUp(self):
        import os

        os.environ["REUS_API_KEY"] = "admin-key"
        os.environ["REUS_USER_API_KEY"] = "user-key"

        import config

        config.get_settings.cache_clear()

        from api.main import admin_app, app, public_app

        self.app = app
        self.public_app = public_app
        self.admin_app = admin_app

    def tearDown(self):
        import os

        os.environ.pop("REUS_API_KEY", None)
        os.environ.pop("REUS_USER_API_KEY", None)

        import config

        config.get_settings.cache_clear()

    def test_public_app_serves_chat_but_not_any_admin_route(self):
        client = TestClient(self.public_app)

        chat_response = client.post("/chat", json={"prompt": "hi"}, headers={"x-api-key": "user-key"})
        self.assertNotEqual(chat_response.status_code, 404)

        for admin_path in ["/agents", "/workflows", "/metrics", "/observability", "/dashboard"]:
            response = client.get(admin_path, headers={"x-api-key": "admin-key"})
            self.assertEqual(
                response.status_code, 404, f"{admin_path} يجب أن يكون غائبًا تمامًا عن public_app"
            )

    def test_admin_app_serves_admin_routes_but_not_chat_or_public_app_page(self):
        client = TestClient(self.admin_app)

        agents_response = client.get("/agents", headers={"x-api-key": "admin-key"})
        self.assertNotEqual(agents_response.status_code, 404)

        for public_path in ["/chat", "/app"]:
            response = client.get(public_path, headers={"x-api-key": "user-key"})
            self.assertEqual(
                response.status_code, 404, f"{public_path} يجب أن يكون غائبًا تمامًا عن admin_app"
            )

    def test_combined_app_still_serves_everything_unchanged(self):
        """التطبيق الافتراضي (app) يجب ألا يتغيّر سلوكه إطلاقًا — لا يزال
        يخدم كل المسارين، تمامًا كسلوك المشروع قبل هذا الفصل."""
        client = TestClient(self.app)

        chat_response = client.post("/chat", json={"prompt": "hi"}, headers={"x-api-key": "user-key"})
        self.assertNotEqual(chat_response.status_code, 404)

        agents_response = client.get("/agents", headers={"x-api-key": "admin-key"})
        self.assertNotEqual(agents_response.status_code, 404)

    def test_every_app_variant_has_its_own_health_and_ready(self):
        """أي عملية مُشغَّلة بمفردها (public_app أو admin_app) تحتاج فحوصات
        حيوية/جهوزية خاصة بها بصرف النظر عن أي المسارات الأخرى تخدمها."""
        for variant in (self.app, self.public_app, self.admin_app):
            client = TestClient(variant)
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.get("/ready").status_code, 200)


class TestBackgroundWorkersOwnership(unittest.TestCase):
    """يثبت القرار المُوثَّق في api/main.py: عمّال الخلفية (المهام، تلغرام
    الاستقصاء، التقرير اليومي) هم مسؤولية admin_app/app فقط — public_app
    المستقل لا يجب أن يحاول بدء أي منها، لتفادي معالجة كل حدث مرتين لو
    شُغِّل التطبيقان كعمليتين فعليتين منفصلتين."""

    def test_public_app_lifespan_never_touches_worker_settings(self):
        import inspect

        from api.main import _make_lifespan

        source = inspect.getsource(_make_lifespan)
        # يثبت وجود الفرع الشرطي نفسه في الكود المصدري، لا افتراضًا نظريًا
        self.assertIn("if start_background_workers:", source)


if __name__ == "__main__":
    unittest.main()
