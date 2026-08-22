"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Read-only local readiness checks used by ``reusctl``.  The doctor never
modifies environment files, downloads models, or contacts external services.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path


PLACEHOLDERS = ("change-me", "generate-a-unique", "change_me", "redacted")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or any(marker in normalized for marker in PLACEHOLDERS)


def check(root: Path, *, strict: bool) -> list[str]:
    issues: list[str] = []
    if sys.version_info < (3, 11):
        issues.append(f"Reus requires Python 3.11+; found {sys.version.split()[0]}.")
    if not (root / ".venv" / "bin" / "python").exists():
        issues.append("No local virtual environment exists; run: bash scripts/reusctl.sh install")

    env_path = root / ".env"
    if not env_path.exists():
        issues.append("No local configuration exists; run install to create a conservative local setup.")
        return issues
    values = load_env(env_path)
    environment = values.get("REUS_ENVIRONMENT", "development").lower()
    for key in ("REUS_API_KEY", "REUS_USER_API_KEY"):
        if is_placeholder(values.get(key, "")):
            issues.append(f"{key} is still empty or a placeholder.")

    if environment == "production" and values.get("REUS_STORAGE_BACKEND") == "postgres" and not values.get("REUS_ENCRYPTION_KEY"):
        issues.append("Production PostgreSQL requires REUS_ENCRYPTION_KEY.")
    if values.get("REUS_TELEGRAM_ENABLED", "false").lower() == "true":
        if is_placeholder(values.get("REUS_TELEGRAM_BOT_TOKEN", "")) or not values.get("REUS_TELEGRAM_ALLOWED_CHAT_IDS", "").strip():
            issues.append("Telegram is enabled without a valid bot token or an administrative chat allowlist.")

    executor = values.get("REUS_TASK_EXECUTOR", "default")
    if executor == "default":
        issues.append("REUS_TASK_EXECUTOR=default does not support /chat; choose ollama or model_router.")
    if executor == "ollama":
        if shutil.which("ollama") is None:
            issues.append("The Ollama executable is required for local chat but is not on PATH.")
        elif strict:
            base_url = values.get("REUS_OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            model = values.get("REUS_OLLAMA_MODEL", "")
            try:
                with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as response:
                    available = response.read().decode("utf-8")
                if model and f'"name":"{model}"' not in available and f'"name": "{model}"' not in available:
                    issues.append(f"Ollama model {model!r} is not listed by /api/tags.")
            except (OSError, urllib.error.URLError):
                issues.append("Local Ollama is unavailable; start the Ollama service before starting chat.")
    return issues


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run read-only local Reus readiness checks.")
    parser.add_argument("--strict", action="store_true", help="Also verify the selected Ollama service and model.")
    arguments = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    issues = check(root, strict=arguments.strict)
    if issues:
        print("Reus Doctor: check did not pass")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Reus Doctor: local readiness checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
