"""Project: Reus | Developer: lotfi Mahiddine | Organization: Reulink.

Generate only missing or placeholder local-development settings. Existing
non-placeholder secrets are deliberately preserved.
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
from pathlib import Path


PLACEHOLDERS = ("change-me", "generate-a-unique", "CHANGE_ME", "REDACTED")
_CHAT_ID_LIST = re.compile(r"^-?\d+(?:,-?\d+)*$")
LOCAL_DEFAULTS = {
    "REUS_ENVIRONMENT": "development",
    "REUS_STORAGE_BACKEND": "memory",
    "REUS_EVENT_BUS_BACKEND": "memory",
    "REUS_TASK_EXECUTOR": "ollama",
    "REUS_OLLAMA_ENABLED": "true",
    "REUS_TELEGRAM_ENABLED": "false",
    "REUS_WORKER_ENABLED": "false",
}


def _needs_value(value: str) -> bool:
    normalized = value.strip()
    return not normalized or any(marker.lower() in normalized.lower() for marker in PLACEHOLDERS)


def _upsert(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            existing = line[len(prefix):]
            if _needs_value(existing):
                lines[index] = f"{prefix}{value}\n"
            return lines
    lines.append(f"{prefix}{value}\n")
    return lines


def _set_exact(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}\n"
            return lines
    lines.append(f"{prefix}{value}\n")
    return lines


def _validate_telegram_settings(bot_token: str, allowed_chat_ids: str) -> tuple[str, str]:
    token = bot_token.strip()
    chat_ids = allowed_chat_ids.strip()
    if not token or not chat_ids:
        raise ValueError("Telegram enablement requires both a bot token and at least one allowed chat ID.")
    if "\n" in bot_token or "\r" in bot_token or "\n" in allowed_chat_ids or "\r" in allowed_chat_ids:
        raise ValueError("Telegram settings cannot contain newlines.")
    if not _CHAT_ID_LIST.fullmatch(chat_ids):
        raise ValueError("Telegram allowed chat IDs must be a comma-separated list of numeric IDs.")
    return token, chat_ids


def configure(
    path: Path,
    *,
    enable_local_chat: bool = False,
    enable_telegram: bool = False,
    telegram_bot_token: str | None = None,
    telegram_allowed_chat_ids: str | None = None,
) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for key, value in LOCAL_DEFAULTS.items():
        lines = _upsert(lines, key, value)
    if enable_local_chat:
        for index, line in enumerate(lines):
            if line.startswith("REUS_TASK_EXECUTOR=default"):
                lines[index] = "REUS_TASK_EXECUTOR=ollama\n"
                break
    if enable_telegram:
        token, chat_ids = _validate_telegram_settings(telegram_bot_token or "", telegram_allowed_chat_ids or "")
        lines = _set_exact(lines, "REUS_TELEGRAM_ENABLED", "true")
        lines = _set_exact(lines, "REUS_TELEGRAM_BOT_TOKEN", token)
        lines = _set_exact(lines, "REUS_TELEGRAM_ALLOWED_CHAT_IDS", chat_ids)
    lines = _upsert(lines, "REUS_API_KEY", secrets.token_urlsafe(32))
    lines = _upsert(lines, "REUS_USER_API_KEY", secrets.token_urlsafe(32))
    path.write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create conservative local Reus settings.")
    parser.add_argument(
        "--enable-local-chat",
        action="store_true",
        help="Change only the untouched default executor to Ollama during first-time local installation.",
    )
    parser.add_argument(
        "--enable-telegram",
        action="store_true",
        help="Read Telegram settings from the process environment and enable the local governance channel without printing secrets.",
    )
    arguments = parser.parse_args()
    configure(
        Path(".env"),
        enable_local_chat=arguments.enable_local_chat,
        enable_telegram=arguments.enable_telegram,
        telegram_bot_token=os.environ.get("REUS_TELEGRAM_BOT_TOKEN"),
        telegram_allowed_chat_ids=os.environ.get("REUS_TELEGRAM_ALLOWED_CHAT_IDS"),
    )
