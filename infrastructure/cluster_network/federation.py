"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Metadata-only federation primitives for the global-scale roadmap.  This module
does not transport prompts, memory, secrets, card data, or execution payloads.
It deliberately provides a local, deterministic directory first; network
discovery and cryptographic attestations must be layered on top of it.
"""
from __future__ import annotations

from dataclasses import dataclass
import time


class FederationPolicyError(ValueError):
    """Raised when an advertisement crosses a trust or metadata boundary."""


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


@dataclass(frozen=True)
class TrustDomain:
    """A human-approved administrative boundary, not a count of node identities."""

    domain_id: str
    root_fingerprint: str
    allowed_capabilities: frozenset[str]

    def validate(self) -> None:
        if not self.domain_id or len(self.domain_id) > 128:
            raise FederationPolicyError("invalid trust domain identifier")
        if not _is_sha256(self.root_fingerprint):
            raise FederationPolicyError("root_fingerprint must be a SHA-256 hexadecimal digest")
        if not self.allowed_capabilities or any(not item or len(item) > 128 for item in self.allowed_capabilities):
            raise FederationPolicyError("trust domain must declare bounded capabilities")


class TrustDomainRegistry:
    """Append-only approval registry; root rotation requires an explicit new domain."""

    def __init__(self) -> None:
        self._domains: dict[str, TrustDomain] = {}

    def approve(self, domain: TrustDomain) -> None:
        domain.validate()
        current = self._domains.get(domain.domain_id)
        if current is not None and current.root_fingerprint != domain.root_fingerprint:
            raise FederationPolicyError("root fingerprint rotation requires a new explicit trust domain")
        self._domains[domain.domain_id] = domain

    def get(self, domain_id: str) -> TrustDomain:
        try:
            return self._domains[domain_id]
        except KeyError as exc:
            raise FederationPolicyError("untrusted domain") from exc


@dataclass(frozen=True)
class CapabilityAdvertisement:
    domain_id: str
    node_id: str
    capabilities: tuple[str, ...]
    capacity_units: int
    expires_at: float
    policy_hash: str
    attestation_hash: str

    def validate(self, now: float) -> None:
        if not self.domain_id or len(self.domain_id) > 128:
            raise FederationPolicyError("invalid domain identifier")
        if not self.node_id or len(self.node_id) > 128:
            raise FederationPolicyError("invalid node identifier")
        if not self.capabilities or any(not item or len(item) > 128 for item in self.capabilities):
            raise FederationPolicyError("capabilities must be a non-empty bounded list")
        if self.capacity_units <= 0:
            raise FederationPolicyError("capacity_units must be positive")
        if self.expires_at <= now:
            raise FederationPolicyError("advertisement is expired")
        for value, name in ((self.policy_hash, "policy_hash"), (self.attestation_hash, "attestation_hash")):
            if not _is_sha256(value):
                raise FederationPolicyError(f"{name} must be a SHA-256 hexadecimal digest")


class FederatedCapabilityDirectory:
    """Trust-scoped directory for scheduling metadata, not remote execution."""

    def __init__(self, *, local_domain_id: str, trusted_domains: set[str], approved_policy_hashes: set[str], registry: TrustDomainRegistry | None = None) -> None:
        if not local_domain_id:
            raise FederationPolicyError("local_domain_id is required")
        self.local_domain_id = local_domain_id
        self._trusted_domains = set(trusted_domains) | {local_domain_id}
        self._approved_policy_hashes = {item.lower() for item in approved_policy_hashes}
        self._registry = registry
        self._advertisements: dict[tuple[str, str], CapabilityAdvertisement] = {}

    def publish(self, advertisement: CapabilityAdvertisement, *, now: float | None = None) -> None:
        now = time.time() if now is None else now
        advertisement.validate(now)
        if advertisement.domain_id not in self._trusted_domains:
            raise FederationPolicyError("untrusted domain")
        if self._registry is not None:
            domain = self._registry.get(advertisement.domain_id)
            if not set(advertisement.capabilities).issubset(domain.allowed_capabilities):
                raise FederationPolicyError("advertised capability exceeds trust-domain policy")
        if advertisement.policy_hash.lower() not in self._approved_policy_hashes:
            raise FederationPolicyError("unapproved policy hash")
        self._advertisements[(advertisement.domain_id, advertisement.node_id)] = advertisement

    def candidates(self, capability: str, *, now: float | None = None) -> list[CapabilityAdvertisement]:
        now = time.time() if now is None else now
        self.purge_expired(now=now)
        return sorted(
            (item for item in self._advertisements.values() if capability in item.capabilities),
            key=lambda item: (-item.capacity_units, item.domain_id, item.node_id),
        )

    def purge_expired(self, *, now: float | None = None) -> int:
        now = time.time() if now is None else now
        expired = [key for key, item in self._advertisements.items() if item.expires_at <= now]
        for key in expired:
            del self._advertisements[key]
        return len(expired)

    def snapshot(self) -> dict:
        """Return scheduling metadata only, suitable for a signed checkpoint."""
        return {
            "local_domain_id": self.local_domain_id,
            "advertisements": [
                {
                    "domain_id": item.domain_id,
                    "node_id": item.node_id,
                    "capabilities": list(item.capabilities),
                    "capacity_units": item.capacity_units,
                    "expires_at": item.expires_at,
                    "policy_hash": item.policy_hash,
                    "attestation_hash": item.attestation_hash,
                }
                for item in self._advertisements.values()
            ],
        }


@dataclass(frozen=True)
class FederatedResourceLease:
    """A bounded cross-domain allocation descriptor; it never carries work data."""

    request_id: str
    work_item_hash: str
    domain_id: str
    node_id: str
    capability: str
    granted_units: int
    expires_at: float
    policy_hash: str

    def validate(self, now: float) -> None:
        if not self.request_id or len(self.request_id) > 128:
            raise FederationPolicyError("invalid resource request identifier")
        if not _is_sha256(self.work_item_hash):
            raise FederationPolicyError("work_item_hash must be a SHA-256 hexadecimal digest")
        if self.granted_units <= 0 or self.expires_at <= now:
            raise FederationPolicyError("resource lease must be positive and unexpired")


class FederatedResourceAllocator:
    """Selects only trusted advertised capacity; payload delivery remains local policy work."""

    def __init__(self, directory: FederatedCapabilityDirectory) -> None:
        self._directory = directory

    def allocate(
        self,
        *,
        request_id: str,
        work_item_hash: str,
        capability: str,
        required_units: int,
        lease_seconds: float,
        now: float | None = None,
    ) -> FederatedResourceLease:
        now = time.time() if now is None else now
        if required_units <= 0 or lease_seconds <= 0:
            raise FederationPolicyError("resource request units and lease duration must be positive")
        if not _is_sha256(work_item_hash):
            raise FederationPolicyError("work_item_hash must be a SHA-256 hexadecimal digest")
        candidates = [item for item in self._directory.candidates(capability, now=now) if item.capacity_units >= required_units]
        if not candidates:
            raise FederationPolicyError("no trusted capacity satisfies the request")
        selected = candidates[0]
        lease = FederatedResourceLease(
            request_id=request_id,
            work_item_hash=work_item_hash.lower(),
            domain_id=selected.domain_id,
            node_id=selected.node_id,
            capability=capability,
            granted_units=required_units,
            expires_at=min(selected.expires_at, now + lease_seconds),
            policy_hash=selected.policy_hash,
        )
        lease.validate(now)
        return lease
