"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

اعداد pytest مشترك عبر كل ملفات الاختبار.

get_admin_rate_limiter() وget_chat_rate_limiter() (container.py) مخبَّآن
عمدًا على مستوى العملية (lru_cache) وهذا سلوك صحيح للإنتاج. لكن هذا يعني
أن كل ملفات الاختبار التي تستدعي مسارات محمية عبر TestClient تتشارك نفس
محدِّد المعدل طوال تشغيل pytest، وتُحتسَب كأنها من نفس العميل، فيتراكم
العداد عبر ملفات لا علاقة بينها.

اكتُشِف هذا فعليًا: 29 اختبارًا فشلت بكود 429 عند تشغيل المجموعة كاملة رغم
نجاحها منفردة. الإصلاح الصحيح: تفريغ حالة المحدِّد بين كل اختبار، لا رفع
السقف نفسه ولا تعطيله.
"""
import os

import pytest

# الاختبارات لا يجب أن تعتمد على .env محلي أو أسرار المستخدم. هذه قيم اختبار
# اصطناعية منخفضة الصلاحية تُضبط قبل استيراد الوحدات التي تستدعي get_settings().
os.environ.setdefault("REUS_API_KEY", "test-admin-secret-12345678901234567890")
os.environ.setdefault("REUS_USER_API_KEY", "test-user-secret-12345678901234567890")
os.environ.setdefault("REUS_ENVIRONMENT", "test")
_TEST_ENVIRONMENT = {
    "REUS_API_KEY": "test-admin-secret-12345678901234567890",
    "REUS_USER_API_KEY": "test-user-secret-12345678901234567890",
    "REUS_ENVIRONMENT": "test",
}


@pytest.fixture(autouse=True)
def _isolate_settings_environment():
    import config

    previous = {key: os.environ.get(key) for key in _TEST_ENVIRONMENT}
    os.environ.update(_TEST_ENVIRONMENT)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    import container

    container.get_admin_rate_limiter.cache_clear()
    container.get_chat_rate_limiter.cache_clear()
    yield
    container.get_admin_rate_limiter.cache_clear()
    container.get_chat_rate_limiter.cache_clear()
