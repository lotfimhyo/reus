# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
TelegramClient: عميل حقيقي وكامل لـ Telegram Bot API عبر httpx مباشرة (بلا SDK
ثقيل)، يدعم إرسال الرسائل واستقبالها عبر Long Polling — الخيار العملي هنا لأنه
لا يتطلب عنوان HTTPS عامًا يستقبل Webhook (بعكس نشر إنتاجي خلف نطاق حقيقي).

قرار هندسي موثّق بصدق: هذا كود إنتاجي كامل وصحيح بروتوكوليًا (نفس بنية استدعاءات
Telegram Bot API الرسمية)، لكن بيئة تطوير هذا المشروع مقيَّدة شبكيًا للوصول إلى
api.anthropic.com فقط (انظر إعدادات الشبكة) — لا يمكنها الوصول إلى api.telegram.org
إطلاقًا، بغض النظر عن وجود رمز بوت صالح. لذلك اختُبر هذا العميل عبر حقن عميل httpx
وهمي (نفس أسلوب اختبار AnthropicModelClient/OpenAIModelClient سابقًا)، وليس عبر
نداء شبكي فعلي. أي بيئة تشغيل حقيقية بلا هذا التقييد يمكنها استخدامه مباشرة بضبط
REUS_TELEGRAM_BOT_TOKEN فقط.
"""
from __future__ import annotations

import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramAPIError(Exception):
    def __init__(self, method: str, description: str):
        super().__init__(f"فشل استدعاء Telegram Bot API ({method}): {description}")


class TelegramClient:
    def __init__(self, bot_token: str, http_client: httpx.Client | None = None) -> None:
        self._token = bot_token
        # السماح بحقن http_client يتيح اختبار المنطق بالكامل دون شبكة أو رمز بوت حقيقيين.
        self._http = http_client or httpx.Client(base_url=TELEGRAM_API_BASE, timeout=35.0)

    def _call(self, method: str, params: dict | None = None) -> dict:
        try:
            response = self._http.post(f"/bot{self._token}/{method}", json=params or {})
        except httpx.HTTPError as exc:
            raise TelegramAPIError(method, f"خطأ شبكة: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise TelegramAPIError(method, f"استجابة غير صالحة (ليست JSON): {exc}") from exc

        if not body.get("ok", False):
            raise TelegramAPIError(method, body.get("description", "unknown error"))
        return body["result"]

    def send_message(self, chat_id: str, text: str) -> None:
        # 4096 هو الحد الأقصى الفعلي لطول رسالة تلغرام؛ نقصّ برفق بدل فشل الإرسال بالكامل
        self._call("sendMessage", {"chat_id": chat_id, "text": text[:4096]})

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict]:
        """
        Long Polling: يُبقي الاتصال مفتوحًا حتى `timeout` ثانية بانتظار رسائل جديدة،
        أو يعود فورًا إن وُجدت رسائل بالفعل. `offset` يمنع استلام نفس الرسالة مرتين.
        """
        params: dict = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", params)

    def close(self) -> None:
        self._http.close()
