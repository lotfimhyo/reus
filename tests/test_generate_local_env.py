"""Project: Reus | Developer: lotfi Mahiddine | Organization: Reulink."""
from pathlib import Path

import pytest

from scripts.generate_local_env import configure


def test_configure_replaces_placeholders_without_overwriting_real_secret(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "REUS_API_KEY=generate-a-unique-admin-secret-at-least-24-chars\n"
        "REUS_USER_API_KEY=existing-real-secret\n"
        "REUS_TASK_EXECUTOR=default\n",
        encoding="utf-8",
    )

    configure(env_path, enable_local_chat=True)

    content = env_path.read_text(encoding="utf-8")
    assert "REUS_API_KEY=generate-a-unique" not in content
    assert "REUS_USER_API_KEY=existing-real-secret" in content
    assert "REUS_TASK_EXECUTOR=ollama" in content


def test_configure_adds_local_safe_defaults(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("REUS_API_KEY=ready\nREUS_USER_API_KEY=ready-user\n", encoding="utf-8")

    configure(env_path)

    content = env_path.read_text(encoding="utf-8")
    assert "REUS_STORAGE_BACKEND=memory" in content
    assert "REUS_TELEGRAM_ENABLED=false" in content


def test_configure_enables_telegram_with_valid_local_settings(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("CUSTOM_SETTING=preserved\nREUS_TELEGRAM_ENABLED=false\n", encoding="utf-8")

    configure(
        env_path,
        enable_telegram=True,
        telegram_bot_token="123456:unit-test-token",
        telegram_allowed_chat_ids="5138453991,-1001234567890",
    )

    content = env_path.read_text(encoding="utf-8")
    assert "CUSTOM_SETTING=preserved" in content
    assert "REUS_TELEGRAM_ENABLED=true" in content
    assert "REUS_TELEGRAM_BOT_TOKEN=123456:unit-test-token" in content
    assert "REUS_TELEGRAM_ALLOWED_CHAT_IDS=5138453991,-1001234567890" in content


@pytest.mark.parametrize("token, chat_ids", [("token\nREUS_API_KEY=injected", "5138453991"), ("token", "chat-id")])
def test_configure_rejects_telegram_injection_and_invalid_chat_ids(tmp_path: Path, token: str, chat_ids: str):
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError):
        configure(
            env_path,
            enable_telegram=True,
            telegram_bot_token=token,
            telegram_allowed_chat_ids=chat_ids,
        )
