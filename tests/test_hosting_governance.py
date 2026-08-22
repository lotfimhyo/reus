"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
import pytest

from infrastructure.hosting_governance import (
    HostingGovernanceError,
    HostingGovernanceAudit,
    HostingAuthorizationStore,
    HostingSearchRequest,
    HostingSearchService,
    HostingOffer,
    HostingOfferCatalog,
    HostingPurchaseGate,
    RemoteControlGate,
)


def _offer(**overrides) -> HostingOffer:
    values = {
        "offer_id": "provider-a-small-eu",
        "provider": "Provider A",
        "plan": "Small",
        "region": "eu-west",
        "monthly_price_minor": 1200,
        "currency": "EUR",
        "billing_period": "monthly",
        "is_free": False,
        "data_boundary": "EU",
        "compute_summary": "2 vCPU / 4 GB RAM",
    }
    values.update(overrides)
    return HostingOffer(**values)


def test_catalog_compares_free_before_paid_offers_without_payment_data():
    catalog = HostingOfferCatalog()
    catalog.publish(_offer())
    catalog.publish(_offer(offer_id="provider-b-free", provider="Provider B", plan="Free", monthly_price_minor=0, is_free=True))

    compared = catalog.compare(region="eu-west")

    assert [offer.offer_id for offer in compared] == ["provider-b-free", "provider-a-small-eu"]
    assert "card" not in repr(compared).lower()


class _StaticOfferSource:
    def discover(self, request: HostingSearchRequest) -> list[HostingOffer]:
        return [_offer(), _offer(offer_id="provider-b-free", provider="Provider B", plan="Free", monthly_price_minor=0, is_free=True)]


def test_search_service_filters_provider_offers_without_credentials_or_checkout():
    offers = HostingSearchService([_StaticOfferSource()]).search(
        HostingSearchRequest(region="eu-west", maximum_monthly_price_minor=1200, currency="EUR")
    )
    assert [offer.offer_id for offer in offers] == ["provider-b-free", "provider-a-small-eu"]
    assert HostingSearchService([_StaticOfferSource()]).search(HostingSearchRequest(free_only=True))[0].is_free


def test_purchase_gate_requires_fresh_matching_one_time_approval():
    offer = _offer()
    gate = HostingPurchaseGate()
    authorization = gate.request(offer, now=100.0, ttl_seconds=10)
    with pytest.raises(HostingGovernanceError, match="explicit approval"):
        gate.consume(authorization, offer, now=101.0)

    approved = gate.approve(authorization, offer, now=101.0)
    consumed = gate.consume(approved, offer, now=102.0)
    assert consumed.consumed_at == 102.0
    with pytest.raises(HostingGovernanceError, match="consumed"):
        gate.consume(consumed, offer, now=103.0)
    with pytest.raises(HostingGovernanceError, match="details changed"):
        gate.approve(gate.request(offer, now=100.0), _offer(monthly_price_minor=1300), now=101.0)


def test_purchase_audit_persists_only_non_sensitive_decision_metadata(tmp_path):
    audit = HostingGovernanceAudit(tmp_path / "hosting-audit.jsonl")
    gate = HostingPurchaseGate(audit=audit)
    authorization = gate.request(_offer(), now=100.0)
    approved = gate.approve(authorization, _offer(), now=101.0)
    gate.consume(approved, _offer(), now=102.0)

    entries = audit.entries()
    assert [entry["event"] for entry in entries] == [
        "hosting_purchase_requested", "hosting_purchase_approved", "hosting_purchase_consumed",
    ]
    assert entries[-1]["amount_minor"] == 1200
    assert "card" not in (tmp_path / "hosting-audit.jsonl").read_text(encoding="utf-8").lower()
    with pytest.raises(HostingGovernanceError, match="forbidden"):
        audit.record("bad", at=103.0, card="not-allowed")


def test_purchase_authorization_store_rejects_expired_or_consumed_state_after_restart(tmp_path):
    offer = _offer()
    store = HostingAuthorizationStore(tmp_path / "authorizations.json")
    gate = HostingPurchaseGate(store=store)
    authorization = gate.request(offer, now=100.0, ttl_seconds=10)
    reloaded = HostingAuthorizationStore(tmp_path / "authorizations.json").load(authorization.authorization_id, now=101.0)
    approved = HostingPurchaseGate(store=store).approve(reloaded, offer, now=101.0)
    assert store.load(approved.authorization_id, now=102.0).approved
    consumed = HostingPurchaseGate(store=store).consume(approved, offer, now=102.0)
    with pytest.raises(HostingGovernanceError, match="consumed"):
        HostingAuthorizationStore(tmp_path / "authorizations.json").load(consumed.authorization_id, now=103.0)
    expired = HostingPurchaseGate(store=store).request(offer, now=100.0, ttl_seconds=1)
    with pytest.raises(HostingGovernanceError, match="expired"):
        store.load(expired.authorization_id, now=101.0)


def test_expired_or_cancelled_authorization_writes_durable_audit_event(tmp_path):
    audit = HostingGovernanceAudit(tmp_path / "audit.jsonl")
    store = HostingAuthorizationStore(tmp_path / "authorizations.json")
    gate = HostingPurchaseGate(audit=audit, store=store)
    expired = gate.expire(gate.request(_offer(), now=100.0, ttl_seconds=1), now=101.0)
    with pytest.raises(HostingGovernanceError, match="expired"):
        store.load(expired.authorization_id, now=102.0)
    cancelled = gate.cancel(gate.request(_offer(), now=100.0, ttl_seconds=10), now=101.0)
    with pytest.raises(HostingGovernanceError, match="cancelled"):
        store.load(cancelled.authorization_id, now=102.0)
    events = [entry["event"] for entry in audit.entries()]
    assert "hosting_purchase_expired" in events
    assert "hosting_purchase_cancelled" in events


def test_remote_control_requires_visible_local_confirmation_and_can_be_revoked():
    gate = RemoteControlGate()
    grant = gate.request(mode="control", device_label="Lotfi laptop", now=100.0, ttl_seconds=10)
    session = grant.session
    assert grant.local_confirmation_key not in repr(session)
    with pytest.raises(HostingGovernanceError, match="key is invalid"):
        gate.confirm_locally(session, "wrong-key", now=101.0)
    confirmed = gate.confirm_locally(session, grant.local_confirmation_key, now=101.0)
    assert confirmed.locally_confirmed_at == 101.0
    revoked = gate.revoke(confirmed, now=102.0)
    with pytest.raises(HostingGovernanceError, match="revoked"):
        gate.confirm_locally(revoked, grant.local_confirmation_key, now=103.0)
    expired = gate.request(mode="view", device_label="Lotfi laptop", now=100.0, ttl_seconds=1)
    with pytest.raises(HostingGovernanceError, match="expired"):
        gate.confirm_locally(expired.session, expired.local_confirmation_key, now=101.0)
