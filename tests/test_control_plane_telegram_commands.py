# Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink
import time
import hashlib
from pathlib import Path

from application.agent_token_service import AgentTokenService
from application.control_plane_telegram_commands import ControlPlaneTelegramCommands
from application.orchestrator_service import OrchestratorService
from application.telegram_service import TelegramService
from config import Settings
from infrastructure.agent_token_repository import InMemoryAgentTokenRepository
from infrastructure.control_plane_pairing_store import ControlPlanePairingStore
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.telegram_link_repository import InMemoryTelegramLinkRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository


def build_service(ttl: float = 300.0):
    repo, bus = InMemoryAgentRepository(), InMemoryEventBus()
    return TelegramService(InMemoryTelegramLinkRepository(), AgentTokenService(InMemoryAgentTokenRepository(), repo), OrchestratorService(InMemoryWorkflowRepository(), repo, bus), bus, admin_chat_ids=frozenset({"admin"}), approval_ttl_seconds=ttl)


def store(tmp_path: Path) -> ControlPlanePairingStore:
    return ControlPlanePairingStore(str(tmp_path / "pairings.json"), str(tmp_path / "pairings.audit.jsonl"))


def test_pairing_registers_hashed_claim_then_sends_generated_key_only_server_to_server_after_approval(tmp_path):
    telegram, delivered, posts = build_service(), [], []
    telegram.set_delivery_callback(lambda _, text: delivered.append(text))
    ControlPlaneTelegramCommands(telegram, Settings(), pairing_store=store(tmp_path), post_json=lambda url, payload: posts.append((url, payload)), new_id=lambda: "fixed-id", new_claim=lambda: "claim-must-never-appear-in-telegram")

    telegram.handle_incoming_message("admin", "/pair_control_plane https://panel.example https://core.example")
    assert len(posts) == 1
    assert posts[0][0] == "https://panel.example/api/reus/pairing/claim"
    assert posts[0][1]["claim_hash"] != "claim-must-never-appear-in-telegram"
    assert "claim-must-never" not in "\n".join(delivered)

    telegram.handle_incoming_message("admin", "/approve panel-fixed-id")
    assert len(posts) == 2
    url, payload = posts[1]
    assert url == "https://panel.example/api/reus/pairing/receive"
    assert payload["core_url"] == "https://core.example"
    assert hashlib.sha256(payload["claim_token"].encode("utf-8")).hexdigest() == posts[0][1]["claim_hash"]
    assert len(payload["user_api_key"]) >= 32
    assert payload["user_api_key"] not in "\n".join(delivered)
    assert payload["claim_token"] not in "\n".join(delivered)

    telegram.handle_incoming_message("admin", "/approve panel-fixed-id")
    assert len(posts) == 2


def test_pairing_expiry_fails_closed_before_key_delivery(tmp_path):
    telegram, posts = build_service(ttl=0.001), []
    ControlPlaneTelegramCommands(telegram, Settings(), pairing_store=store(tmp_path), post_json=lambda url, payload: posts.append((url, payload)), new_id=lambda: "expiring")
    telegram.handle_incoming_message("admin", "/pair_control_plane https://panel.example https://core.example")
    time.sleep(0.01)
    telegram.handle_incoming_message("admin", "/approve panel-expiring")
    assert len(posts) == 1


def test_pairing_rejects_non_https_remote_url_without_secret_exposure(tmp_path):
    telegram, delivered, posts = build_service(), [], []
    telegram.set_delivery_callback(lambda _, text: delivered.append(text))
    ControlPlaneTelegramCommands(telegram, Settings(), pairing_store=store(tmp_path), post_json=lambda url, payload: posts.append((url, payload)))
    telegram.handle_incoming_message("admin", "/pair_control_plane http://panel.example https://core.example")
    assert posts == []
    assert "HTTPS" in delivered[-1]
    assert "claim" not in delivered[-1]
