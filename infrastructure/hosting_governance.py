"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Governance primitives for hosting discovery, purchase approval and remote
control.  They intentionally do not hold card details, invoke a provider API,
or open a desktop connection.  Integrations must consume the short-lived
authorizations produced here after separate user confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import secrets
import time
from typing import Protocol
from uuid import uuid4


class HostingGovernanceError(ValueError):
    """Raised when an offer, approval, or session crosses a safety boundary."""


class HostingGovernanceAudit:
    """Append-only JSONL audit that intentionally accepts metadata only."""

    _forbidden = {"card", "cvv", "password", "token", "local_confirmation_key", "session_key"}

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, *, at: float, **metadata: object) -> None:
        if not event or any(key.lower() in self._forbidden for key in metadata):
            raise HostingGovernanceError("audit metadata includes a forbidden or invalid field")
        payload = {"event": event, "at": at, **metadata}
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")

    def entries(self) -> list[dict[str, object]]:
        if not self._path.exists():
            return []
        return [json.loads(line) for line in self._path.read_text(encoding="utf-8").splitlines() if line]


@dataclass(frozen=True)
class HostingOffer:
    offer_id: str
    provider: str
    plan: str
    region: str
    monthly_price_minor: int
    currency: str
    billing_period: str
    is_free: bool
    data_boundary: str
    compute_summary: str

    def validate(self) -> None:
        if not self.offer_id or not self.provider or not self.plan or not self.region:
            raise HostingGovernanceError("hosting offer requires stable identity and provider details")
        if self.monthly_price_minor < 0:
            raise HostingGovernanceError("hosting offer price cannot be negative")
        if self.is_free and self.monthly_price_minor != 0:
            raise HostingGovernanceError("free hosting offer must have zero price")
        if not self.currency or len(self.currency) != 3 or not self.billing_period:
            raise HostingGovernanceError("hosting offer requires currency and billing period")

    def detail_hash(self) -> str:
        self.validate()
        payload = "|".join(
            [self.offer_id, self.provider, self.plan, self.region, str(self.monthly_price_minor), self.currency, self.billing_period, self.data_boundary, self.compute_summary]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class HostingOfferCatalog:
    """Stores inspected offers only; adapters may later populate it from providers."""

    def __init__(self) -> None:
        self._offers: dict[str, HostingOffer] = {}

    def publish(self, offer: HostingOffer) -> None:
        offer.validate()
        self._offers[offer.offer_id] = offer

    def compare(self, *, region: str | None = None, free_only: bool = False) -> list[HostingOffer]:
        offers = list(self._offers.values())
        if region:
            offers = [offer for offer in offers if offer.region == region]
        if free_only:
            offers = [offer for offer in offers if offer.is_free]
        return sorted(offers, key=lambda offer: (not offer.is_free, offer.monthly_price_minor, offer.provider, offer.plan))


@dataclass(frozen=True)
class HostingSearchRequest:
    region: str | None = None
    maximum_monthly_price_minor: int | None = None
    currency: str | None = None
    free_only: bool = False
    require_persistent_compute: bool = True


class HostingOfferSource(Protocol):
    """A provider adapter returns public offer metadata only, never credentials."""

    def discover(self, request: HostingSearchRequest) -> list[HostingOffer]: ...


class HostingSearchService:
    """Combines trusted provider adapters into a reviewable catalog; no checkout exists here."""

    def __init__(self, sources: list[HostingOfferSource]) -> None:
        self._sources = tuple(sources)

    def search(self, request: HostingSearchRequest) -> list[HostingOffer]:
        if request.maximum_monthly_price_minor is not None and request.maximum_monthly_price_minor < 0:
            raise HostingGovernanceError("maximum monthly price cannot be negative")
        catalog = HostingOfferCatalog()
        for source in self._sources:
            for offer in source.discover(request):
                offer.validate()
                if request.region and offer.region != request.region:
                    continue
                if request.free_only and not offer.is_free:
                    continue
                if request.currency and offer.currency.upper() != request.currency.upper():
                    continue
                if request.maximum_monthly_price_minor is not None and offer.monthly_price_minor > request.maximum_monthly_price_minor:
                    continue
                catalog.publish(offer)
        return catalog.compare(region=request.region, free_only=request.free_only)


@dataclass(frozen=True)
class PurchaseAuthorization:
    authorization_id: str
    offer_id: str
    detail_hash: str
    amount_minor: int
    currency: str
    billing_period: str
    expires_at: float
    approved_at: float | None = None
    consumed_at: float | None = None
    expired_at: float | None = None
    cancelled_at: float | None = None

    @property
    def approved(self) -> bool:
        return self.approved_at is not None


class HostingAuthorizationStore:
    """Minimal durable state for finite purchase approvals; no credentials are stored."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, authorization: PurchaseAuthorization) -> None:
        records = self._records()
        records[authorization.authorization_id] = {
            "authorization_id": authorization.authorization_id,
            "offer_id": authorization.offer_id,
            "detail_hash": authorization.detail_hash,
            "amount_minor": authorization.amount_minor,
            "currency": authorization.currency,
            "billing_period": authorization.billing_period,
            "expires_at": authorization.expires_at,
            "approved_at": authorization.approved_at,
            "consumed_at": authorization.consumed_at,
            "expired_at": authorization.expired_at,
            "cancelled_at": authorization.cancelled_at,
        }
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(records, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self._path)

    def load(self, authorization_id: str, *, now: float | None = None) -> PurchaseAuthorization:
        now = time.time() if now is None else now
        authorization = self.load_raw(authorization_id)
        if authorization.cancelled_at is not None:
            raise HostingGovernanceError("purchase authorization is cancelled")
        if authorization.expired_at is not None:
            raise HostingGovernanceError("purchase authorization has expired")
        if now >= authorization.expires_at:
            raise HostingGovernanceError("purchase authorization has expired")
        if authorization.consumed_at is not None:
            raise HostingGovernanceError("purchase authorization is already consumed")
        return authorization

    def load_raw(self, authorization_id: str) -> PurchaseAuthorization:
        """Load durable authorization state without applying lifecycle checks."""
        try:
            record = self._records()[authorization_id]
        except KeyError as exc:
            raise HostingGovernanceError("purchase authorization is not present in durable storage") from exc
        return PurchaseAuthorization(**record)

    def _records(self) -> dict[str, dict[str, object]]:
        if not self._path.exists():
            return {}
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HostingGovernanceError("durable authorization store is invalid") from exc
        if not isinstance(value, dict):
            raise HostingGovernanceError("durable authorization store has invalid shape")
        return value


class HostingPurchaseGate:
    """One-time approval gate; provider adapters must call consume immediately before checkout."""

    def __init__(self, *, audit: HostingGovernanceAudit | None = None, store: HostingAuthorizationStore | None = None) -> None:
        self._audit = audit
        self._store = store
        self._current: dict[str, PurchaseAuthorization] = {}

    def request(self, offer: HostingOffer, *, ttl_seconds: float = 300.0, now: float | None = None) -> PurchaseAuthorization:
        now = time.time() if now is None else now
        offer.validate()
        if ttl_seconds <= 0:
            raise HostingGovernanceError("purchase authorization ttl must be positive")
        authorization = PurchaseAuthorization(
            authorization_id=str(uuid4()),
            offer_id=offer.offer_id,
            detail_hash=offer.detail_hash(),
            amount_minor=offer.monthly_price_minor,
            currency=offer.currency.upper(),
            billing_period=offer.billing_period,
            expires_at=now + ttl_seconds,
        )
        self._record("hosting_purchase_requested", authorization, now)
        self._persist(authorization)
        return authorization

    def approve(self, authorization: PurchaseAuthorization, offer: HostingOffer, *, now: float | None = None) -> PurchaseAuthorization:
        now = time.time() if now is None else now
        authorization = self._latest(authorization)
        self._assert_current(authorization, offer, now)
        if authorization.approved:
            raise HostingGovernanceError("purchase authorization is already approved")
        approved = replace(authorization, approved_at=now)
        self._record("hosting_purchase_approved", approved, now)
        self._persist(approved)
        return approved

    def consume(self, authorization: PurchaseAuthorization, offer: HostingOffer, *, now: float | None = None) -> PurchaseAuthorization:
        now = time.time() if now is None else now
        authorization = self._latest(authorization)
        self._assert_current(authorization, offer, now)
        if not authorization.approved:
            raise HostingGovernanceError("purchase authorization requires explicit approval")
        if authorization.consumed_at is not None:
            raise HostingGovernanceError("purchase authorization is already consumed")
        consumed = replace(authorization, consumed_at=now)
        self._record("hosting_purchase_consumed", consumed, now)
        self._persist(consumed)
        return consumed

    def expire(self, authorization: PurchaseAuthorization, *, now: float | None = None) -> PurchaseAuthorization:
        now = time.time() if now is None else now
        authorization = self._latest(authorization)
        if authorization.consumed_at is not None:
            raise HostingGovernanceError("consumed purchase authorization cannot expire")
        if authorization.cancelled_at is not None or authorization.expired_at is not None:
            raise HostingGovernanceError("purchase authorization is already closed")
        if now < authorization.expires_at:
            raise HostingGovernanceError("purchase authorization is not yet expired")
        expired = replace(authorization, expired_at=now)
        self._record("hosting_purchase_expired", expired, now)
        self._persist(expired)
        return expired

    def cancel(self, authorization: PurchaseAuthorization, *, now: float | None = None) -> PurchaseAuthorization:
        now = time.time() if now is None else now
        authorization = self._latest(authorization)
        if authorization.consumed_at is not None:
            raise HostingGovernanceError("consumed purchase authorization cannot be cancelled")
        if authorization.cancelled_at is not None or authorization.expired_at is not None:
            raise HostingGovernanceError("purchase authorization is already closed")
        cancelled = replace(authorization, cancelled_at=now)
        self._record("hosting_purchase_cancelled", cancelled, now)
        self._persist(cancelled)
        return cancelled

    def _record(self, event: str, authorization: PurchaseAuthorization, now: float) -> None:
        if self._audit is not None:
            self._audit.record(
                event,
                at=now,
                authorization_id=authorization.authorization_id,
                offer_id=authorization.offer_id,
                detail_hash=authorization.detail_hash,
                amount_minor=authorization.amount_minor,
                currency=authorization.currency,
                billing_period=authorization.billing_period,
            )

    def _persist(self, authorization: PurchaseAuthorization) -> None:
        self._current[authorization.authorization_id] = authorization
        if self._store is not None:
            self._store.save(authorization)

    def _latest(self, authorization: PurchaseAuthorization) -> PurchaseAuthorization:
        if self._store is not None:
            return self._store.load_raw(authorization.authorization_id)
        return self._current.get(authorization.authorization_id, authorization)

    @staticmethod
    def _assert_current(authorization: PurchaseAuthorization, offer: HostingOffer, now: float) -> None:
        if authorization.cancelled_at is not None:
            raise HostingGovernanceError("purchase authorization is cancelled")
        if authorization.expired_at is not None:
            raise HostingGovernanceError("purchase authorization has expired")
        if authorization.consumed_at is not None:
            raise HostingGovernanceError("purchase authorization is already consumed")
        if now >= authorization.expires_at:
            raise HostingGovernanceError("purchase authorization has expired")
        if authorization.offer_id != offer.offer_id or authorization.detail_hash != offer.detail_hash():
            raise HostingGovernanceError("hosting offer details changed; request a new authorization")


@dataclass(frozen=True)
class RemoteControlSession:
    session_id: str
    mode: str
    device_label: str
    expires_at: float
    session_key_hash: str
    locally_confirmed_at: float | None = None
    revoked_at: float | None = None


@dataclass(frozen=True)
class RemoteControlGrant:
    """The raw local confirmation key is emitted once and is never persisted."""

    session: RemoteControlSession
    local_confirmation_key: str


class RemoteControlGate:
    """Issues short-lived session descriptors; a desktop client must enforce local consent."""

    _modes = {"view", "control"}

    def request(self, *, mode: str, device_label: str, ttl_seconds: float = 300.0, now: float | None = None) -> RemoteControlGrant:
        now = time.time() if now is None else now
        if mode not in self._modes or not device_label or ttl_seconds <= 0:
            raise HostingGovernanceError("invalid remote-control session request")
        local_confirmation_key = secrets.token_urlsafe(32)
        session = RemoteControlSession(
            str(uuid4()),
            mode,
            device_label,
            now + ttl_seconds,
            hashlib.sha256(local_confirmation_key.encode("utf-8")).hexdigest(),
        )
        return RemoteControlGrant(session, local_confirmation_key)

    def confirm_locally(self, session: RemoteControlSession, local_confirmation_key: str, *, now: float | None = None) -> RemoteControlSession:
        now = time.time() if now is None else now
        self._assert_open(session, now)
        received_key_hash = hashlib.sha256(local_confirmation_key.encode("utf-8")).hexdigest()
        if not secrets.compare_digest(session.session_key_hash, received_key_hash):
            raise HostingGovernanceError("remote-control session key is invalid")
        if session.locally_confirmed_at is not None:
            raise HostingGovernanceError("remote-control session is already confirmed")
        return replace(session, locally_confirmed_at=now)

    def revoke(self, session: RemoteControlSession, *, now: float | None = None) -> RemoteControlSession:
        now = time.time() if now is None else now
        if session.revoked_at is not None:
            return session
        return replace(session, revoked_at=now)

    @staticmethod
    def _assert_open(session: RemoteControlSession, now: float) -> None:
        if session.revoked_at is not None:
            raise HostingGovernanceError("remote-control session is revoked")
        if now >= session.expires_at:
            raise HostingGovernanceError("remote-control session has expired")
