"""Project: Reus | Developer: lotfi Mahiddine | Organization: Reulink.

Generate only missing or placeholder local-development settings. Existing
non-placeholder secrets are deliberately preserved.
"""
from __future__ import annotations

import argparse
import secrets
from pathlib import Path


PLACEHOLDERS = ("change-me", "generate-a-unique", "CHANGE_ME", "REDACTED")
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


def configure(path: Path, *, enable_local_chat: bool = False) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for key, value in LOCAL_DEFAULTS.items():
        lines = _upsert(lines, key, value)
    if enable_local_chat:
        for index, line in enumerate(lines):
            if line.startswith("REUS_TASK_EXECUTOR=default"):
                lines[index] = "REUS_TASK_EXECUTOR=ollama\n"
                break
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
    arguments = parser.parse_args()
    configure(Path(".env"), enable_local_chat=arguments.enable_local_chat)
