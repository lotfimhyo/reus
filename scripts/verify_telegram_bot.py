"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Verify the configured Telegram bot with the read-only Bot API `getMe` method.
The bot token is read from the process environment or a local `.env` file by
the regular Settings layer and is never printed, logged, or written by this
script.
"""
from __future__ import annotations

import json

from config import get_settings
from infrastructure.telegram_client import TelegramAPIError, TelegramClient


def main() -> int:
    settings = get_settings()
    if not settings.telegram_enabled:
        raise SystemExit("Telegram verification requires REUS_TELEGRAM_ENABLED=true.")

    client = TelegramClient(bot_token=settings.telegram_bot_token)
    try:
        identity = client.get_me()
    except TelegramAPIError as exc:
        raise SystemExit(f"Telegram bot verification failed: {exc}") from exc
    finally:
        client.close()

    safe_identity = {
        key: identity[key]
        for key in ("id", "is_bot", "first_name", "username", "can_join_groups", "can_read_all_group_messages", "supports_inline_queries")
        if key in identity
    }
    print(json.dumps({"telegram_bot_verified": True, "bot": safe_identity}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
