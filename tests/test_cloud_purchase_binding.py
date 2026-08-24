# Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink
from unittest.mock import MagicMock

import pytest

from infrastructure.cloud.deployment_manager import CloudDeploymentManager, CloudLimitExceeded
from infrastructure.cloud.provider_base import CloudConfig
from infrastructure.hosting_governance import HostingPurchaseGate


def _manager() -> tuple[CloudDeploymentManager, MagicMock, HostingPurchaseGate]:
    provider = MagicMock()
    provider.list_instances.return_value = []
    provider.estimate_monthly_cost.return_value = 5.25
    gate = HostingPurchaseGate()
    manager = CloudDeploymentManager(provider, purchase_gate=gate)
    manager.configure(
        CloudConfig(
            provider="example",
            api_token="test-only",
            region="region-a",
            size="small",
            max_instances=2,
            budget_cap_usd_per_month=20,
        )
    )
    return manager, provider, gate


def test_provider_creation_requires_matching_approved_one_time_authorization():
    manager, provider, gate = _manager()
    proposal = manager.propose_new_instance("replacement-a")
    offer = manager.purchase_offer(proposal)
    authorization = gate.approve(gate.request(offer), offer)

    manager.execute_new_instance("replacement-a", authorization=authorization, offer=offer)

    provider.create_instance.assert_called_once()
    with pytest.raises(Exception, match="already consumed"):
        manager.execute_new_instance("replacement-a", authorization=authorization, offer=offer)


def test_provider_creation_refuses_missing_or_changed_purchase_authorization():
    manager, provider, gate = _manager()
    proposal = manager.propose_new_instance("replacement-a")
    offer = manager.purchase_offer(proposal)

    with pytest.raises(CloudLimitExceeded, match="one-time authorization"):
        manager.execute_new_instance("replacement-a")

    authorization = gate.approve(gate.request(offer), offer)
    changed = manager.purchase_offer(manager.propose_new_instance("replacement-b"))
    with pytest.raises(Exception, match="details changed"):
        manager.execute_new_instance("replacement-a", authorization=authorization, offer=changed)
    provider.create_instance.assert_not_called()
