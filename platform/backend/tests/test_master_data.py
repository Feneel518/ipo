from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.ingestion.bse import BSEAdapter
from app.ingestion.nse import NSEAdapter
from app.ingestion.service import (
    _detail_is_due,
    _failure_retry,
    _next_failure_count,
    _next_refresh,
    _set_if_present,
)
from app.ingestion.types import NormalizedIssue
from app.models import Exchange, ExchangeListing, Lifecycle, MarketType, Segment
from app.schemas import IpoDetail


def issue(exchange: Exchange = Exchange.NSE) -> NormalizedIssue:
    return NormalizedIssue(
        exchange=exchange,
        segment=Segment.MAINBOARD,
        source_id="TEST",
        endpoint="fixture",
        source_url="https://example.test",
        company_name="Test Limited",
        normalized_name="test",
        symbol="TEST",
        series="EQ" if exchange == Exchange.NSE else None,
        lifecycle=Lifecycle.OPEN,
        issue_size_shares=Decimal("8317190"),
        raw={"symbol": "TEST"},
    )


def test_nse_detail_normalizes_master_data_and_bid_rules():
    payload = {
        "issueInfo": {
            "symbol": "TEST",
            "dataList": [
                {"title": "Issue Type", "value": "100% Book Building"},
                {"title": "Price Range", "value": "Rs. 200 to Rs. 212"},
                {"title": "Face Value", "value": "Rs. 10 per Equity Share"},
                {"title": "Tick Size", "value": "Re. 1"},
                {"title": "Bid Lot", "value": "70 Equity Shares and multiples thereof"},
                {"title": "Minimum Order Quantity", "value": "70 Equity Shares"},
                {
                    "title": "Maximum Subscription Amount for Retail Investor",
                    "value": "Rs. 2,00,000",
                },
                {
                    "title": "Maximum Bid Quantity for QIB Investors",
                    "value": "83,17,190 equity shares in multiples of 70",
                },
            ],
        }
    }

    enriched = NSEAdapter()._merge_detail(issue(), payload)

    assert enriched.market_type == MarketType.BOOK_BUILT
    assert enriched.price_low == Decimal("200")
    assert enriched.price_high == Decimal("212")
    assert enriched.tick_size == Decimal("1")
    assert enriched.lot_size == 70
    assert enriched.minimum_bid_quantity == 70
    assert enriched.minimum_retail_investment == Decimal("14840")
    assert enriched.issue_size_crore == Decimal("176.324428")
    assert enriched.issue_size_crore_is_estimated is True
    rules = {rule.category: rule for rule in enriched.bid_rules}
    assert rules["RETAIL"].maximum_subscription_amount == Decimal("200000")
    assert rules["QIB"].maximum_bid_quantity == 8317190


def test_bse_detail_keeps_symbol_separate_from_internal_scrip_id():
    payload = {"status": "success"}
    detail = {
        "ScripCode": "4279",
        "ScripName": "Test Limited",
        "Symbol": "TEST",
        "Issue_Size_No_of_shares": "8317190",
        "Price_Band": "200.00-212.00",
        "Face_Value": "10.00",
        "Tick_Size": "1.00",
        "Market_Lot": "70",
        "Minimum_Bid_Quantity": "70",
        "Maximum_Bid_Quantity_For_Qualified_Institutional_Investors": "8317190",
        "Maximum_Bid_Quantity_For_Qualified_Non_Institutional_Investors": "5940850",
    }

    enriched = BSEAdapter()._merge_detail(issue(Exchange.BSE), detail, payload)

    assert enriched.symbol == "TEST"
    assert enriched.scrip_code is None
    assert enriched.market_type == MarketType.BOOK_BUILT
    assert enriched.minimum_retail_investment == Decimal("14840")
    assert {rule.category for rule in enriched.bid_rules} == {"QIB", "NIB"}


def test_fixed_price_issue_and_source_issue_size_are_not_marked_estimated():
    normalized = issue().model_copy(
        update={
            "price_low": Decimal("51"),
            "price_high": Decimal("51"),
            "final_issue_price": Decimal("51"),
            "minimum_bid_quantity": 2000,
            "issue_size_crore": Decimal("25.5"),
            "market_type": MarketType.FIXED_PRICE,
        }
    ).with_calculated_values()

    assert normalized.minimum_retail_investment == Decimal("102000")
    assert normalized.issue_size_crore == Decimal("25.5")
    assert normalized.issue_size_crore_is_estimated is False


def test_lifecycle_refresh_schedule_and_backoff():
    now = datetime(2026, 8, 19, 12, tzinfo=UTC)
    assert _next_refresh(Lifecycle.UPCOMING, None, now) == (now + timedelta(hours=6), None)
    assert _next_refresh(Lifecycle.OPEN, None, now) == (now + timedelta(minutes=5), None)
    assert _next_refresh(Lifecycle.CLOSED, None, now) == (now + timedelta(days=1), None)
    assert _next_refresh(Lifecycle.LISTED, date(2026, 8, 13), now) == (
        now + timedelta(days=1),
        None,
    )
    assert _next_refresh(Lifecycle.LISTED, date(2026, 8, 12), now) == (None, now)
    assert _next_refresh(Lifecycle.CANCELLED, None, now) == (None, now)
    assert _failure_retry(now, 1) == now + timedelta(hours=1)
    assert _failure_retry(now, 10) == now + timedelta(hours=24)
    assert _next_failure_count(None) == 1
    assert _next_failure_count(2) == 3


def test_due_logic_and_api_contract_fields():
    now = datetime(2026, 8, 19, 12, tzinfo=UTC)
    listing = ExchangeListing(
        ipo_id=1,
        exchange=Exchange.NSE,
        segment=Segment.MAINBOARD,
        source_id="TEST",
        source_url="https://example.test",
        master_data_last_fetched_at=now - timedelta(hours=2),
        next_refresh_at=now - timedelta(minutes=1),
    )
    assert _detail_is_due(listing, now) is True
    listing.master_data_finalized_at = now
    assert _detail_is_due(listing, now) is False
    expected = {
        "platform",
        "exchange_platform",
        "nse_symbol",
        "nse_series",
        "bse_symbol",
        "bse_scrip_code",
        "market_type",
        "final_issue_price",
        "tick_size",
        "minimum_bid_quantity",
        "minimum_retail_investment",
        "bid_rules",
        "master_data_last_fetched_at",
    }
    assert expected <= set(IpoDetail.model_fields)


def test_malformed_detail_contract_and_null_protection():
    try:
        NSEAdapter()._merge_detail(issue(), {"issueInfo": {"dataList": []}})
    except ValueError as exc:
        assert "contract changed" in str(exc)
    else:
        raise AssertionError("Malformed NSE detail should be rejected")

    class Target:
        value = "known"

    target = Target()
    _set_if_present(target, {"value": None})
    assert target.value == "known"
