"""Project: Reus | Developer: lotfi Mahiddine | Organization: Reulink."""
from pathlib import Path

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
