"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

A secure, allowlist-limited .env reader and writer. It allows selected
Telegram, task-executor, and model settings to be changed from a control plane
without opening and manually editing the file, while retaining file safety:

- An explicit `ALLOWED_SETTINGS_KEYS` allowlist prevents writing every other
  variable through this path. REUS_API_KEY and REUS_USER_API_KEY are excluded
  deliberately because web-based, unchecked changes would create a clear
  privilege-escalation risk.
- Values containing a newline are rejected. Without this check, a value such as
  `x\nREUS_API_KEY=attacker_key` could inject a new variable outside the allowlist.
- All unrelated lines and comments are preserved exactly; no full rewrite loses
  existing manual customization.
"""
from __future__ import annotations

import re

ALLOWED_SETTINGS_KEYS = frozenset(
    {
        "REUS_TELEGRAM_ENABLED",
        "REUS_TELEGRAM_BOT_TOKEN",
        "REUS_TELEGRAM_ALLOWED_CHAT_IDS",
        "REUS_TASK_EXECUTOR",
        "REUS_ANTHROPIC_API_KEY",
        "REUS_OPENAI_API_KEY",
        "REUS_GOOGLE_API_KEY",
        "REUS_OLLAMA_ENABLED",
        "REUS_OLLAMA_BASE_URL",
        "REUS_OLLAMA_MODEL",
    }
)

# Values never returned to the UI in plaintext; report configured or empty only.
_SECRET_KEYS = frozenset(
    {"REUS_TELEGRAM_BOT_TOKEN", "REUS_ANTHROPIC_API_KEY", "REUS_OPENAI_API_KEY", "REUS_GOOGLE_API_KEY"}
)


class InvalidSettingKey(Exception):
    pass


class InvalidSettingValue(Exception):
    pass


def read_env_file(env_path: str = ".env") -> dict[str, str]:
    """Return only allowlisted keys. Non-sensitive fields retain their values;
    sensitive fields are reported as configured or empty and no real secret is
    ever returned to the browser UI."""
    result: dict[str, str] = {}
    try:
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return result

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key in ALLOWED_SETTINGS_KEYS:
            if key in _SECRET_KEYS:
                result[key] = "***configured***" if value.strip() else ""
            else:
                result[key] = value.strip()
    return result


def update_env_file(updates: dict[str, str], env_path: str = ".env") -> None:
    """Update only keys in `updates`, all of which must be allowlisted. Replace
    existing values, append missing keys, and preserve every other line,
    including sensitive REUS_API_KEY and REUS_USER_API_KEY entries."""
    for key, value in updates.items():
        if key not in ALLOWED_SETTINGS_KEYS:
            raise InvalidSettingKey(f"'{key}' is not editable through this path")
        if "\n" in value or "\r" in value:
            raise InvalidSettingValue(f"Value for '{key}' contains a newline and was rejected")

    try:
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    remaining = dict(updates)
    new_lines = []
    for line in lines:
        stripped = line.strip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=", stripped) if stripped and not stripped.startswith("#") else None
        if match and match.group(1) in remaining:
            key = match.group(1)
            new_lines.append(f"{key}={remaining.pop(key)}\n")
        else:
            new_lines.append(line)

    for key, value in remaining.items():
        new_lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
