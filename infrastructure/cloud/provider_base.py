# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
CloudProvider: a provider-agnostic interface for provisioning compute
instances. `DigitalOceanProvider` (digitalocean_provider.py) is the
reference implementation; adding AWS/Hetzner/etc. later means implementing
this same interface, nothing else changes.

SECURITY MODEL:
  - The system NEVER discovers or chooses providers/credentials on its
    own. A human (via Telegram /configure_cloud, restricted to authorized
    chat_ids) supplies the provider, API token, and hard limits.
  - `max_instances` and `budget_cap_usd_per_month` are enforced BEFORE any
    provisioning call is even proposed — the system cannot exceed them no
    matter what a task or a model decides it wants.
  - Every instance creation AND destruction goes through the same
    Telegram approval gate as self-built capabilities (see
    cloud/telegram_commands.py) — nothing is provisioned or destroyed
    without an explicit /approve from an authorized chat.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CloudConfig:
    provider: str
    api_token: str
    region: str
    size: str  # provider-specific plan/size identifier
    max_instances: int
    budget_cap_usd_per_month: float
    # سكربت cloud-init/user-data الفعلي الذي يُشغَّل عند إقلاع الخادم لأول
    # مرة — انظر infrastructure/cloud/node_cloud_init.py. "" يعني: خادم
    # فارغ، لا شيء يُشغَّل تلقائيًا (السلوك الأصلي قبل دعم نشر العقد).
    user_data: str = ""


@dataclass
class InstanceInfo:
    id: str
    name: str
    provider: str
    region: str
    size: str
    status: str
    ip_address: Optional[str] = None
    monthly_cost_usd: float = 0.0


class CloudProvider(ABC):
    @abstractmethod
    def create_instance(self, name: str, config: CloudConfig) -> InstanceInfo:
        ...

    @abstractmethod
    def list_instances(self, config: CloudConfig) -> List[InstanceInfo]:
        ...

    @abstractmethod
    def destroy_instance(self, instance_id: str, config: CloudConfig) -> None:
        ...

    @abstractmethod
    def estimate_monthly_cost(self, config: CloudConfig) -> float:
        ...
