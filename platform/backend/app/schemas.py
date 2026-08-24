from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import Exchange, Lifecycle, MarketType, Segment


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    exchange: Exchange
    segment: Segment
    symbol: str | None
    series: str | None
    scrip_code: str | None
    source_status: str | None
    issue_price: Decimal | None
    listing_price: Decimal | None
    listing_close: Decimal | None
    listing_gain_percent: Decimal | None
    source_url: str
    is_stale: bool
    master_data_last_fetched_at: datetime | None


class BidRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    exchange: Exchange
    category: str
    minimum_bid_quantity: int | None
    maximum_bid_quantity: int | None
    maximum_subscription_amount: Decimal | None


class ReservationOut(BaseModel):
    category: str
    parent_category: str | None
    shares: Decimal
    percentage_net: Decimal | None
    percentage_total: Decimal
    max_allottees: int | None
    minimum_bid_quantity: int | None
    minimum_allotment_quantity: int | None
    source_url: str
    source_type: str
    as_of_date: date | None
    is_actual: bool
    is_derived: bool


class ReservationSummaryOut(BaseModel):
    total_issue_shares: Decimal
    net_offer_shares: Decimal
    reserved_shares: Decimal
    rows: list[ReservationOut]


class LotApplicationOut(BaseModel):
    category: str
    application_kind: str
    lots: int
    shares: int
    amount: Decimal


class IpoCard(BaseModel):
    id: int
    company_name: str
    slug: str
    lifecycle: Lifecycle
    open_date: date | None
    close_date: date | None
    allotment_date: date | None
    allotment_date_is_estimated: bool
    refund_date: date | None
    refund_date_is_estimated: bool
    credit_date: date | None
    credit_date_is_estimated: bool
    expected_listing_date: date | None
    listing_date: date | None
    price_low: Decimal | None
    price_high: Decimal | None
    lot_size: int | None
    listings: list[ListingOut]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    document_type: str
    title: str
    url: str


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    exchange: Exchange
    snapshot_date: date
    captured_at: datetime
    observed_at: datetime
    category: str
    shares_reserved_for_category: Decimal | None
    raw_exchange_bid_quantity: Decimal | None
    applications: Decimal | None
    calculated_subscription: Decimal | None
    source_reported_multiple: Decimal | None
    source: str
    bid_data_scope: str


class IpoDetail(IpoCard):
    isin: str | None
    issue_type: str
    market_type: MarketType
    platform: Segment | None
    exchange_platform: str | None
    nse_symbol: str | None
    nse_series: str | None
    bse_symbol: str | None
    bse_scrip_code: str | None
    final_issue_price: Decimal | None
    face_value: Decimal | None
    tick_size: Decimal | None
    minimum_bid_quantity: int | None
    minimum_retail_investment: Decimal | None
    issue_size_shares: Decimal | None
    issue_size_crore: Decimal | None
    issue_size_crore_is_estimated: bool
    registrar: str | None
    lead_managers: list[str] | None
    documents: list[DocumentOut]
    subscriptions: list[SubscriptionOut]
    bid_rules: list[BidRuleOut]
    reservation_summary: ReservationSummaryOut | None
    lot_size_applications: list[LotApplicationOut]
    master_data_last_fetched_at: datetime | None
    master_data_sources: list[str]
    last_updated_at: datetime
    sources: list[str]


class PageMeta(BaseModel):
    next_cursor: int | None
    last_updated_at: datetime | None


class IpoPage(BaseModel):
    data: list[IpoCard]
    meta: PageMeta


class CalendarEvent(BaseModel):
    ipo_slug: str
    company_name: str
    event_type: str
    event_date: date
    lifecycle: Lifecycle


class SummaryOut(BaseModel):
    open: int
    upcoming: int
    listed: int
    mainboard: int
    sme: int
    last_updated_at: datetime | None
