from datetime import UTC, datetime
from decimal import Decimal

from app.ingestion.service import _store_subscription_snapshot, _subscription_content_hash
from app.ingestion.types import Subscription
from app.models import Exchange


class FakeSession:
    def __init__(self, existing_id=None):
        self.existing_id = existing_id
        self.added = []

    def scalar(self, _statement):
        return self.existing_id

    def add(self, value):
        self.added.append(value)


def subscription(bids: str) -> Subscription:
    return Subscription(
        category="RETAIL",
        shares_reserved_for_category=Decimal("100"),
        raw_exchange_bid_quantity=Decimal(bids),
        calculated_subscription=Decimal(bids) / Decimal("100"),
        captured_at=datetime(2026, 8, 19, 10, 0, tzinfo=UTC),
        source="https://example.test/subscription",
    )


def test_content_hash_changes_when_subscription_numbers_change():
    assert _subscription_content_hash(subscription("50")) != _subscription_content_hash(
        subscription("75")
    )


def test_identical_observation_is_not_inserted_again():
    db = FakeSession(existing_id=12)

    inserted = _store_subscription_snapshot(
        db, 7, Exchange.NSE, subscription("50"), datetime(2026, 8, 19, 10, 5, tzinfo=UTC)
    )

    assert inserted is False
    assert db.added == []


def test_changed_figures_append_a_new_immutable_observation():
    db = FakeSession()
    observed_at = datetime(2026, 8, 19, 10, 5, tzinfo=UTC)

    inserted = _store_subscription_snapshot(
        db, 7, Exchange.NSE, subscription("75"), observed_at
    )

    assert inserted is True
    assert len(db.added) == 1
    snapshot = db.added[0]
    assert snapshot.raw_exchange_bid_quantity == Decimal("75")
    assert snapshot.calculated_subscription == Decimal("0.75")
    assert snapshot.observed_at == observed_at
    assert snapshot.content_hash == _subscription_content_hash(subscription("75"))
