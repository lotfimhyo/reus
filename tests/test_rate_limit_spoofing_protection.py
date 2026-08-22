"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

يثبت إصلاح ثغرة حقيقية: X-Forwarded-For كان يُوثَق به دائمًا بلا شرط في
تحديد هوية العميل لتحديد المعدل — أي مهاجم يستطيع تجاوز كل تحديد معدل في
المشروع (بما فيه حماية تخمين المفتاح الإداري نفسها) بمجرد تزوير قيمة
مختلفة لهذه الترويسة مع كل طلب. الافتراضي الآن: تجاهل الترويسة تمامًا
واستخدام عنوان TCP الفعلي (REUS_TRUST_PROXY_HEADERS=false)، إلا إذا أكَّد
المُشغِّل صراحة أنه خلف وكيل عكسي حقيقي.
"""
from __future__ import annotations

import os
import unittest

from infrastructure.rate_limiter import client_key_from_request


class _FakeRequest:
    def __init__(self, headers: dict, client_host: str = "203.0.113.5"):
        self.headers = headers
        self.client = type("Client", (), {"host": client_host})()


class TestClientKeySpoofingProtection(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("REUS_TRUST_PROXY_HEADERS", None)
        import config

        config.get_settings.cache_clear()

    def test_forwarded_for_is_ignored_by_default_uses_real_tcp_peer(self):
        request = _FakeRequest({"x-forwarded-for": "1.2.3.4"}, client_host="203.0.113.5")
        self.assertEqual(client_key_from_request(request), "203.0.113.5")

    def test_spoofed_header_cannot_generate_unlimited_distinct_keys_by_default(self):
        """الاختبار الحاسم: قيم مختلفة لـX-Forwarded-For يجب أن تُحلَّل جميعًا
        لنفس المفتاح (عنوان TCP الفعلي) طالما لم يُفعَّل الوثوق بالوكيل —
        هذا هو ما يمنع تجاوز تحديد المعدل بتزوير الترويسة."""
        keys = {
            client_key_from_request(_FakeRequest({"x-forwarded-for": f"10.0.0.{i}"}, "203.0.113.5"))
            for i in range(20)
        }
        self.assertEqual(keys, {"203.0.113.5"})

    def test_forwarded_for_is_honored_when_trust_proxy_headers_explicitly_enabled(self):
        os.environ["REUS_TRUST_PROXY_HEADERS"] = "true"
        import config

        config.get_settings.cache_clear()

        request = _FakeRequest({"x-forwarded-for": "1.2.3.4, 203.0.113.5"})
        self.assertEqual(client_key_from_request(request), "1.2.3.4")

    def test_falls_back_to_tcp_peer_when_no_client_info_at_all(self):
        request = _FakeRequest({})
        request.client = None
        self.assertEqual(client_key_from_request(request), "unknown")


if __name__ == "__main__":
    unittest.main()
