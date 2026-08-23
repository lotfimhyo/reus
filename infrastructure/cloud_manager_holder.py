"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

CloudDeploymentManager cannot be constructed as a fixed singleton during
composition because it depends on a provider selected only when an authorized
operator runs `/configure_cloud` through Telegram. Before this holder existed,
the manager was private state inside CloudTelegramCommands, leaving the read-only
HTTP control-plane path unable to inspect it even though the manager's limits and
listing logic are not Telegram-specific.

CloudManagerHolder is a small shared container. CloudTelegramCommands populates
it only after successful `/configure_cloud`; `/nodes` reads it only. This gives
one source of truth instead of two states that could diverge. It performs no
provider call, purchase, or resource creation itself."""
from __future__ import annotations

from typing import Optional

from infrastructure.cloud.deployment_manager import CloudDeploymentManager


class CloudManagerHolder:
    def __init__(self) -> None:
        self.manager: Optional[CloudDeploymentManager] = None
