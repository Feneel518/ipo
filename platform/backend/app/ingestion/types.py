from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models import Exchange, Lifecycle, MarketType, Segment


class Subscription(BaseModel):
    category: str = "TOTAL"
    shares_reserved_for_category: Decimal | None = None
    raw_exchange_bid_quantity: Decimal | None = None
    applications: Decimal | None = None
    calculated_subscription: Decimal | None = None
    source_reported_multiple: Decimal | None = None
    captured_at: datetime | None = None
    source: str
    bid_data_scope: str = "ALL_EXCHANGES"


class BidRuleData(BaseModel):
    category: str
    minimum_bid_quantity: int | None = None
    maximum_bid_quantity: int | None = None
    maximum_subscription_amount: Decimal | None = None


class NormalizedIssue(BaseModel):
    exchange: Exchange
    segment: Segment
    source_id: str
    endpoint: str
    source_url: str
    company_name: str
    normalized_name: str
    symbol: str | None = None
    series: str | None = None
    scrip_code: str | None = None
    source_status: str | None = None
    isin: str | None = None
    lifecycle: Lifecycle
    open_date: date | None = None
    close_date: date | None = None
    listing_date: date | None = None
    price_low: Decimal | None = None
    price_high: Decimal | None = None
    final_issue_price: Decimal | None = None
    face_value: Decimal | None = None
    tick_size: Decimal | None = None
    lot_size: int | None = None
    minimum_bid_quantity: int | None = None
    minimum_retail_investment: Decimal | None = None
    issue_size_shares: Decimal | None = None
    issue_size_crore: Decimal | None = None
    issue_size_crore_is_estimated: bool = False
    market_type: MarketType = MarketType.UNKNOWN
    registrar: str | None = None
    lead_managers: list[str] | None = None
    issue_price: Decimal | None = None
    listing_price: Decimal | None = None
    listing_close: Decimal | None = None
    documents: list[tuple[str, str, str]] = Field(default_factory=list)
    subscriptions: list[Subscription] = Field(default_factory=list)
    bid_rules: list[BidRuleData] = Field(default_factory=list)
    raw: dict[str, Any]
    detail_raw: dict[str, Any] | None = None
    detail_endpoint: str | None = None
    detail_fetched_at: datetime | None = None
    detail_error: str | None = None
    subscription_raw: dict[str, Any] | None = None
    subscription_endpoint: str | None = None

    def with_calculated_values(self) -> "NormalizedIssue":
        updates: dict[str, Any] = {}
        applicable_price = self.final_issue_price or self.price_high
        if self.minimum_bid_quantity is not None and applicable_price is not None:
            updates["minimum_retail_investment"] = (
                Decimal(self.minimum_bid_quantity) * applicable_price
            )
        if (
            self.issue_size_crore is None
            and self.issue_size_shares is not None
            and applicable_price
        ):
            updates["issue_size_crore"] = (
                self.issue_size_shares * applicable_price / Decimal("10000000")
            )
            updates["issue_size_crore_is_estimated"] = True
        return self.model_copy(update=updates)

    @staticmethod
    def fetched_now() -> datetime:
        return datetime.now(UTC)
