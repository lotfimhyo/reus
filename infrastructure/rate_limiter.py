# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""محدد معدل آمن ومحدود الذاكرة لنوافذ زمنية متحركة.

**المطور:** lotfi Mahiddine

التنفيذ محلي داخل العملية، لكنه لا يسمح بنمو الحالة بلا حد: تُنظف
النوافذ المنتهية، وتُحذف أقدم المفاتيح عند تجاوز السقف. في النشر متعدد النسخ
يجب استخدام محدد موزع على مستوى البوابة أو Redis؛ هذه الطبقة تبقى واجهة قابلة
للاستبدال حتى لا تتسرب تفاصيل التخزين إلى المسارات.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict, deque


class RateLimiter:
    """واجهة محدد المعدل التي تعتمد عليها طبقة HTTP."""

    def allow(self, key: str) -> tuple[bool, float]:
        """يعيد (مسموح؟، ثوانٍ حتى إعادة المحاولة إن رُفض)."""
        raise NotImplementedError


class InMemoryRateLimiter(RateLimiter):
    """نافذة متحركة مع حالة محدودة وقفل صريح.

    القفل الواحد مقصود هنا: يزيل سباقات إنشاء/حذف المفاتيح التي قد تفقد
    تحديثاً تحت حمل متوازٍ. معدل طلبات المصادقة صغير نسبياً، وصحة عداد الحماية
    أهم من تحسين متناهٍ في التوازي قد ينتج عنه تجاوز للحد.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        *,
        max_keys: int = 10_000,
        cleanup_interval_seconds: float = 60.0,
    ):
        if max_requests <= 0 or window_seconds <= 0:
            raise ValueError("max_requests وwindow_seconds يجب أن يكونا أكبر من صفر")
        if max_keys <= 0 or cleanup_interval_seconds <= 0:
            raise ValueError("max_keys وcleanup_interval_seconds يجب أن يكونا أكبر من صفر")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._max_keys = max_keys
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._last_cleanup = time.monotonic()
        self._lock = threading.RLock()

    def _cleanup_locked(self, now: float) -> None:
        if now - self._last_cleanup < self._cleanup_interval_seconds:
            return
        cutoff = now - self._window_seconds
        for key in list(self._hits):
            timestamps = self._hits[key]
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()
            if not timestamps:
                del self._hits[key]
        while len(self._hits) > self._max_keys:
            self._hits.popitem(last=False)
        self._last_cleanup = now

    def allow(self, key: str) -> tuple[bool, float]:
        now = time.monotonic()
        if len(key) > 256:
            key = hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()
        cutoff = now - self._window_seconds
        with self._lock:
            self._cleanup_locked(now)
            timestamps = self._hits.setdefault(key, deque())
            self._hits.move_to_end(key)
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()
            if len(timestamps) >= self._max_requests:
                retry_after = timestamps[0] + self._window_seconds - now
                return False, max(retry_after, 0.0)
            timestamps.append(now)
            return True, 0.0


def client_key_from_request(request) -> str:
    """يستخرج هوية عميل مستقرة دون الوثوق بالترويسة القابلة للتزوير افتراضياً."""
    from config import get_settings

    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client = forwarded.split(",")[0].strip()
            if client:
                return client
    return request.client.host if request.client and request.client.host else "unknown"
