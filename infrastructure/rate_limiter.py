# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""A secure, memory-bounded sliding-window rate limiter.

**Founder:** Lotfi Mahiddine | **Organization:** Reulink

The implementation is local to the process but does not permit unbounded state:
expired windows are cleaned and the oldest keys are evicted above the cap. A
multi-instance deployment should use a gateway- or Redis-level distributed
limiter. This layer remains replaceable so storage details do not leak into
routes.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict, deque


class RateLimiter:
    """Rate-limiter interface used by the HTTP layer."""

    def allow(self, key: str) -> tuple[bool, float]:
        """Return whether a request is allowed and retry seconds if denied."""
        raise NotImplementedError


class InMemoryRateLimiter(RateLimiter):
    """A sliding window with bounded state and an explicit lock.

    One lock deliberately prevents key-creation and eviction races that could
    lose an update under concurrent load. Authentication traffic is relatively
    low, and a correct protective counter matters more than marginal parallelism
    that could permit an over-limit request.
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
            raise ValueError("max_requests and window_seconds must be greater than zero")
        if max_keys <= 0 or cleanup_interval_seconds <= 0:
            raise ValueError("max_keys and cleanup_interval_seconds must be greater than zero")
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
    """Extract a stable client identity without trusting forgeable headers by default."""
    from config import get_settings

    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client = forwarded.split(",")[0].strip()
            if client:
                return client
    return request.client.host if request.client and request.client.host else "unknown"
