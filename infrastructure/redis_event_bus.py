# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
RedisEventBus is a distributed EventBus implementation over Redis Pub/Sub.

Unlike InMemoryEventBus, which is synchronous because it runs within one
process, RedisEventBus is inherently asynchronous. A message is published to
Redis and any subscribing process on the same or another server receives it
through its own listener thread with modest network delay. This is what permits
agents and workers to distribute across multiple nodes.

Every event is also written to local structured logs regardless of subscribers,
preserving the event-recording security requirement.
"""
from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict

import redis

from infrastructure.event_bus import Event, EventBus, Subscriber

logger = logging.getLogger("reus_veritas.events")

CHANNEL_PREFIX = "reus_veritas:events"
WILDCARD_PATTERN = f"{CHANNEL_PREFIX}:*"


class RedisEventBus(EventBus):
    def __init__(self, redis_url: str) -> None:
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._client.ping()  # Fail early and clearly when Redis is unavailable.
        self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        self._exact_handlers: dict[str, list[Subscriber]] = defaultdict(list)
        self._wildcard_handlers: list[Subscriber] = []
        self._lock = threading.Lock()
        self._listener_thread = None
        self._subscribed_channels: set[str] = set()
        self._subscribed_wildcard = False

    def publish(self, event: Event) -> None:
        channel = f"{CHANNEL_PREFIX}:{event.name}"
        message = json.dumps(
            {"name": event.name, "payload": event.payload, "timestamp": event.timestamp.isoformat()},
            default=str,
            ensure_ascii=False,
        )
        logger.info(
            "event_published",
            extra={"event_name": event.name, "payload": event.payload, "ts": event.timestamp.isoformat()},
        )
        self._client.publish(channel, message)

    def subscribe(self, event_name: str, handler: Subscriber) -> None:
        with self._lock:
            if event_name == "*":
                self._wildcard_handlers.append(handler)
                if not self._subscribed_wildcard:
                    self._pubsub.psubscribe(**{WILDCARD_PATTERN: self._dispatch_pmessage})
                    self._subscribed_wildcard = True
            else:
                channel = f"{CHANNEL_PREFIX}:{event_name}"
                self._exact_handlers[event_name].append(handler)
                if channel not in self._subscribed_channels:
                    self._pubsub.subscribe(**{channel: self._dispatch_message})
                    self._subscribed_channels.add(channel)
            self._ensure_listener_running()

    def _ensure_listener_running(self) -> None:
        if self._listener_thread is None or not self._listener_thread.is_alive():
            self._listener_thread = self._pubsub.run_in_thread(sleep_time=0.01, daemon=True)

    def _parse(self, raw_data: str) -> Event:
        from datetime import datetime

        body = json.loads(raw_data)
        return Event(name=body["name"], payload=body["payload"], timestamp=datetime.fromisoformat(body["timestamp"]))

    def _dispatch_message(self, message: dict) -> None:
        event = self._parse(message["data"])
        for handler in self._exact_handlers.get(event.name, []):
            handler(event)

    def _dispatch_pmessage(self, message: dict) -> None:
        event = self._parse(message["data"])
        for handler in self._wildcard_handlers:
            handler(event)

    def close(self) -> None:
        """Stop the listener thread safely for application shutdown or test cleanup."""
        if self._listener_thread is not None:
            self._listener_thread.stop()
            self._listener_thread.join(timeout=1.0)  # Wait for actual thread exit before closing connections.
            self._listener_thread = None
        self._pubsub.close()
        self._client.close()
