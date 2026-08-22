"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
import pytest

from infrastructure.cluster_network.federation import (
    CapabilityAdvertisement,
    FederatedCapabilityDirectory,
    FederatedResourceAllocator,
    FederationPolicyError,
    TrustDomain,
    TrustDomainRegistry,
)


POLICY = "a" * 64
ATTESTATION = "b" * 64


def _advertisement(**overrides) -> CapabilityAdvertisement:
    values = {
        "domain_id": "region-eu",
        "node_id": "worker-1",
        "capabilities": ("text.inference", "summarization"),
        "capacity_units": 8,
        "expires_at": 200.0,
        "policy_hash": POLICY,
        "attestation_hash": ATTESTATION,
    }
    values.update(overrides)
    return CapabilityAdvertisement(**values)


def test_directory_only_accepts_trusted_short_lived_metadata_and_routes_by_capability():
    directory = FederatedCapabilityDirectory(
        local_domain_id="region-local", trusted_domains={"region-eu"}, approved_policy_hashes={POLICY}
    )
    directory.publish(_advertisement(), now=100.0)

    candidates = directory.candidates("text.inference", now=101.0)

    assert [item.node_id for item in candidates] == ["worker-1"]
    snapshot = directory.snapshot()
    assert "prompt" not in repr(snapshot)
    assert "memory" not in repr(snapshot)


def test_directory_rejects_untrusted_expired_or_policy_mismatched_advertisements():
    directory = FederatedCapabilityDirectory(
        local_domain_id="region-local", trusted_domains={"region-eu"}, approved_policy_hashes={POLICY}
    )
    with pytest.raises(FederationPolicyError, match="untrusted"):
        directory.publish(_advertisement(domain_id="unknown"), now=100.0)
    with pytest.raises(FederationPolicyError, match="expired"):
        directory.publish(_advertisement(expires_at=100.0), now=100.0)
    with pytest.raises(FederationPolicyError, match="unapproved"):
        directory.publish(_advertisement(policy_hash="c" * 64), now=100.0)


def test_trust_domain_registry_blocks_root_rotation_and_capability_escalation():
    registry = TrustDomainRegistry()
    registry.approve(TrustDomain("region-eu", "d" * 64, frozenset({"text.inference"})))
    directory = FederatedCapabilityDirectory(
        local_domain_id="region-local",
        trusted_domains={"region-eu"},
        approved_policy_hashes={POLICY},
        registry=registry,
    )
    with pytest.raises(FederationPolicyError, match="exceeds"):
        directory.publish(_advertisement(), now=100.0)
    with pytest.raises(FederationPolicyError, match="rotation"):
        registry.approve(TrustDomain("region-eu", "e" * 64, frozenset({"text.inference"})))


def test_resource_allocator_uses_trusted_capacity_and_transmits_only_work_hash():
    directory = FederatedCapabilityDirectory(
        local_domain_id="region-local", trusted_domains={"region-eu"}, approved_policy_hashes={POLICY}
    )
    directory.publish(_advertisement(capacity_units=12), now=100.0)
    lease = FederatedResourceAllocator(directory).allocate(
        request_id="request-1",
        work_item_hash="c" * 64,
        capability="text.inference",
        required_units=4,
        lease_seconds=20,
        now=100.0,
    )

    assert lease.node_id == "worker-1"
    assert lease.granted_units == 4
    assert lease.work_item_hash == "c" * 64
    assert "prompt" not in repr(lease)
    with pytest.raises(FederationPolicyError, match="no trusted capacity"):
        FederatedResourceAllocator(directory).allocate(
            request_id="request-2", work_item_hash="c" * 64, capability="text.inference",
            required_units=99, lease_seconds=20, now=100.0,
        )
