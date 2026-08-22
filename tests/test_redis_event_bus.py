# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
اختبارات تكامل على خادم Redis فعلي (يعمل محليًا في هذه البيئة). بما أن Redis Pub/Sub
غير متزامن بطبيعته (خيط استماع منفصل)، تنتظر هذه الاختبارات وصول الأحداث عبر
threading.Event بمهلة زمنية معقولة بدل افتراض التسليم الفوري.
"""
from __future__ import annotations

import threading
import time

import pytest

from infrastructure.event_bus import Event
from infrastructure.redis_event_bus import RedisEventBus

REDIS_URL = "redis://localhost:6379/0"


@pytest.fixture
def bus():
    b = RedisEventBus(redis_url=REDIS_URL)
    yield b
    b.close()


def _wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_exact_subscription_receives_matching_event(bus: RedisEventBus):
    received: list[Event] = []
    bus.subscribe("agent.created", lambda e: received.append(e))
    time.sleep(0.1)  # إتاحة وقت لاكتمال الاشتراك قبل النشر

    bus.publish(Event(name="agent.created", payload={"agent_id": "a1"}))

    assert _wait_for(lambda: len(received) == 1)
    assert received[0].payload["agent_id"] == "a1"


def test_exact_subscription_ignores_other_events(bus: RedisEventBus):
    received: list[Event] = []
    bus.subscribe("task.completed", lambda e: received.append(e))
    time.sleep(0.1)

    bus.publish(Event(name="task.failed", payload={}))
    time.sleep(0.3)

    assert received == []


def test_wildcard_subscription_receives_all_events(bus: RedisEventBus):
    received: list[str] = []
    bus.subscribe("*", lambda e: received.append(e.name))
    time.sleep(0.1)

    bus.publish(Event(name="workflow.created", payload={}))
    bus.publish(Event(name="task.ready", payload={}))

    assert _wait_for(lambda: len(received) == 2)
    assert set(received) == {"workflow.created", "task.ready"}


def test_multiple_handlers_on_same_event_all_invoked(bus: RedisEventBus):
    counter = {"a": 0, "b": 0}
    bus.subscribe("agent.created", lambda e: counter.__setitem__("a", counter["a"] + 1))
    bus.subscribe("agent.created", lambda e: counter.__setitem__("b", counter["b"] + 1))
    time.sleep(0.1)

    bus.publish(Event(name="agent.created", payload={}))

    assert _wait_for(lambda: counter["a"] == 1 and counter["b"] == 1)


def test_separate_bus_instances_communicate_across_processes(bus: RedisEventBus):
    """يحاكي عقدتين منفصلتين: ناشر على اتصال ومشترك على اتصال مختلف تمامًا."""
    subscriber_bus = RedisEventBus(redis_url=REDIS_URL)
    try:
        received = threading.Event()
        payloads = []

        def handler(event: Event) -> None:
            payloads.append(event.payload)
            received.set()

        subscriber_bus.subscribe("workflow.completed", handler)
        time.sleep(0.1)

        bus.publish(Event(name="workflow.completed", payload={"workflow_id": "wf-123"}))

        assert received.wait(timeout=2.0) is True
        assert payloads[0]["workflow_id"] == "wf-123"
    finally:
        subscriber_bus.close()
