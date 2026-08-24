# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
CloudDeploymentManager: the enforcement point for the hard limits a human
sets via /configure_cloud. No proposal is even generated if it would
exceed `max_instances` or `budget_cap_usd_per_month` — this check happens
BEFORE the Telegram approval step, not instead of it. Both gates apply:
limits enforced in code, AND explicit human approval per action.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from infrastructure.cloud.provider_base import CloudConfig, CloudProvider, InstanceInfo
from infrastructure.hosting_governance import HostingOffer, HostingPurchaseGate, PurchaseAuthorization


class CloudLimitExceeded(RuntimeError):
    pass


@dataclass
class DeploymentProposal:
    name: str
    provider: str
    region: str
    size: str
    estimated_monthly_cost_usd: float
    current_instance_count: int
    current_monthly_spend_usd: float

    def describe(self) -> str:
        return (
            f"Create '{self.name}' on {self.provider} ({self.region}, {self.size})\n"
            f"Estimated cost: ${self.estimated_monthly_cost_usd:.2f}/mo\n"
            f"Current usage: {self.current_instance_count} instance(s), "
            f"${self.current_monthly_spend_usd:.2f}/mo already committed"
        )


class CloudDeploymentManager:
    def __init__(self, provider: CloudProvider, *, purchase_gate: HostingPurchaseGate | None = None):
        self._provider = provider
        self._config: Optional[CloudConfig] = None
        self._purchase_gate = purchase_gate

    def configure(self, config: CloudConfig) -> None:
        self._config = config

    @property
    def is_configured(self) -> bool:
        return self._config is not None

    def set_user_data(self, user_data: str) -> None:
        """Updates the user_data/cloud-init script for the next
        `execute_new_instance` call only. It is not stored as a durable
        `configure()` setting, preventing a role-specific node script (from
        `/deploy_node <role>`) from leaking into a later deployment with a
        different role that lacks an explicit update."""
        if not self._config:
            raise CloudLimitExceeded("cloud provider not configured — use /configure_cloud first")
        self._config.user_data = user_data

    def _current_usage(self) -> Tuple[List[InstanceInfo], float]:
        instances = self._provider.list_instances(self._config)
        spend = sum(i.monthly_cost_usd for i in instances)
        return instances, spend

    def propose_new_instance(self, name: str) -> DeploymentProposal:
        if not self._config:
            raise CloudLimitExceeded("cloud provider not configured — use /configure_cloud first")

        instances, current_spend = self._current_usage()

        if len(instances) >= self._config.max_instances:
            raise CloudLimitExceeded(
                f"refused: {len(instances)}/{self._config.max_instances} instances already running "
                f"(max_instances limit reached)"
            )

        estimated_cost = self._provider.estimate_monthly_cost(self._config)
        if current_spend + estimated_cost > self._config.budget_cap_usd_per_month:
            raise CloudLimitExceeded(
                f"refused: ${current_spend:.2f} + ${estimated_cost:.2f} would exceed the "
                f"${self._config.budget_cap_usd_per_month:.2f}/mo budget cap"
            )

        return DeploymentProposal(
            name=name,
            provider=self._config.provider,
            region=self._config.region,
            size=self._config.size,
            estimated_monthly_cost_usd=estimated_cost,
            current_instance_count=len(instances),
            current_monthly_spend_usd=current_spend,
        )

    def purchase_offer(self, proposal: DeploymentProposal) -> HostingOffer:
        """Produce the immutable price/configuration contract for one VM."""
        if not self._config:
            raise CloudLimitExceeded("cloud provider not configured")
        return HostingOffer(
            offer_id=f"{proposal.provider}:{proposal.region}:{proposal.size}:{proposal.name}",
            provider=proposal.provider,
            plan=proposal.size,
            region=proposal.region,
            monthly_price_minor=round(proposal.estimated_monthly_cost_usd * 100),
            currency="USD",
            billing_period="monthly",
            is_free=False,
            data_boundary=f"provider region {proposal.region}",
            compute_summary=f"one {proposal.size} node named {proposal.name}",
        )

    def execute_new_instance(
        self,
        name: str,
        *,
        authorization: PurchaseAuthorization | None = None,
        offer: HostingOffer | None = None,
    ) -> InstanceInfo:
        """Create exactly one approved resource and consume its authorization.

        A provider adapter cannot be reached unless the authorization matches
        the full reviewed offer and has been approved. Consumption occurs
        immediately before creation, so a network retry cannot charge twice.
        """
        if not self._config:
            raise CloudLimitExceeded("cloud provider not configured")
        if self._purchase_gate is None or authorization is None or offer is None:
            raise CloudLimitExceeded("cloud purchase requires a configured one-time authorization")
        self._purchase_gate.consume(authorization, offer)
        return self._provider.create_instance(name, self._config)

    def list_instances(self) -> List[InstanceInfo]:
        if not self._config:
            return []
        return self._provider.list_instances(self._config)

    def destroy_instance(self, instance_id: str) -> None:
        if not self._config:
            raise CloudLimitExceeded("cloud provider not configured")
        self._provider.destroy_instance(instance_id, self._config)
