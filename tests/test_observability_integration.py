# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from application.cloud_telegram_commands import CloudTelegramCommands
from application.telegram_service import TelegramService
from infrastructure.agent_factory.builder import AgentBuilder
from infrastructure.agent_factory.manifest import AgentSpec, TestCase
from infrastructure.capability_binder import AgentCapabilityBinder, CapabilityBindingRejected
from infrastructure.cognitive_core.capability import CapabilityLayer
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.event_bus import InMemoryEventBus


class _FakeOrchestrator:
    pass


class _FakeTokenService:
    pass


class _FakeLinkRepo:
    def get_by_chat_id(self, chat_id):
        return None

    def add(self, link):
        pass

    def delete(self, chat_id):
        pass


@pytest.fixture
def bus():
    return InMemoryEventBus()


@pytest.fixture
def captured(bus):
    events = []
    bus.subscribe("*", events.append)
    return events


def test_capability_binder_publishes_built_and_rejected_events(bus, captured, tmp_path):
    audit_log = AppendOnlyAuditLog(path=str(tmp_path / "audit.jsonl"))
    capability_layer = CapabilityLayer(audit_log=audit_log, data_dir=str(tmp_path))
    local_executor = LocalExecutor()
    builder = AgentBuilder(output_dir=str(tmp_path / "agents"))
    binder = AgentCapabilityBinder(builder, capability_layer, local_executor, event_bus=bus)

    binder.build_and_bind(
        AgentSpec(name="uppercaser", capability="text.uppercase", description="d", template="uppercase",
                  test_cases=[TestCase(input="a", expected_output="A")])
    )
    with pytest.raises(CapabilityBindingRejected):
        binder.build_and_bind(
            AgentSpec(name="bad", capability="x", description="", template="uppercase", test_cases=[])
        )

    names = [e.name for e in captured]
    assert "capability.built" in names
    assert "capability.rejected" in names


def test_admin_command_denial_is_published(bus, captured):
    service = TelegramService(_FakeLinkRepo(), _FakeTokenService(), _FakeOrchestrator(), bus,
                               admin_chat_ids=frozenset({"admin1"}))
    CloudTelegramCommands(service, provider_factory=lambda name: object(), event_bus=bus)

    service.handle_incoming_message("intruder", "/configure_cloud provider=digitalocean token=x "
                                                 "region=nyc3 size=s max_instances=1 budget_cap=5")

    assert any(e.name == "admin.command_denied" and e.payload["chat_id"] == "intruder" for e in captured)


def test_cloud_configured_event_never_leaks_the_token(bus, captured):
    service = TelegramService(_FakeLinkRepo(), _FakeTokenService(), _FakeOrchestrator(), bus,
                               admin_chat_ids=frozenset({"admin1"}))
    CloudTelegramCommands(
        service,
        provider_factory=lambda name: object(),
        event_bus=bus,
        token_resolver=lambda _provider: "test-secret-token",
    )

    service.handle_incoming_message("admin1", "/configure_cloud provider=digitalocean "
                                               "region=nyc3 size=s max_instances=1 budget_cap=5 "
                                               'source_fetch_cmd="git clone https://example.invalid/reus.git /opt/reus"')

    configured_events = [e for e in captured if e.name == "cloud.configured"]
    assert configured_events
    for e in configured_events:
        assert "test-secret-token" not in str(e.payload)
        assert "token" not in e.payload
