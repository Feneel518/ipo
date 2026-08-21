from datetime import date
from decimal import Decimal

from app.ingestion.normalize import (
    decimal_value,
    extract_schedule_dates,
    lifecycle,
    normalize_name,
    parse_date,
    price_band,
    segment,
)
from app.lifecycle import effective_lifecycle
from app.models import Ipo, Lifecycle, Segment


def test_indian_price_band_and_dates():
    assert price_band("Rs. 1,025 to Rs. 1,080") == (Decimal("1025"), Decimal("1080"))
    assert price_band("200.00-212.00") == (Decimal("200.00"), Decimal("212.00"))
    assert price_band("₹152.00 - ₹160.00") == (Decimal("152.00"), Decimal("160.00"))
    assert parse_date("19-Aug-2026") == date(2026, 8, 19)
    assert parse_date("2026-08-19T00:00:00") == date(2026, 8, 19)


def test_exchange_schedule_dates_are_extracted_from_keys_and_title_rows():
    schedule = extract_schedule_dates(
        {
            "allotmentDate": "24-Aug-2026",
            "timeline": [
                {"title": "Initiation of Refunds", "value": "On or before August 25, 2026"},
                {"title": "Credit of Equity Shares", "value": "25-August-2026"},
            ],
        }
    )

    assert schedule == {
        "allotment_date": date(2026, 8, 24),
        "refund_date": date(2026, 8, 25),
        "credit_date": date(2026, 8, 25),
    }
    assert decimal_value("2.5328946E7") == Decimal("25328946")


def test_name_and_segment_normalization():
    assert normalize_name("Example India Private Limited") == "example"
    assert segment("NSE SME") == Segment.SME
    assert segment("MainBoard") == Segment.MAINBOARD


def test_lifecycle_is_date_driven():
    today = date(2026, 8, 19)
    assert lifecycle("", date(2026, 8, 20), None, None, today=today) == Lifecycle.UPCOMING
    assert lifecycle("", date(2026, 8, 18), date(2026, 8, 20), None, today=today) == Lifecycle.OPEN
    assert lifecycle("", date(2026, 8, 1), date(2026, 8, 3), None, today=today) == Lifecycle.CLOSED
    assert lifecycle("", None, None, date(2026, 8, 19), today=today) == Lifecycle.LISTED
    assert (
        lifecycle(
            "Issue postponed", date(2026, 8, 1), date(2026, 8, 3), None, today=today
        )
        == Lifecycle.CANCELLED
    )


def test_effective_lifecycle_corrects_stale_persisted_status():
    ipo = Ipo(
        company_name="Sunshine Pictures Limited",
        normalized_name="sunshine pictures",
        slug="sunshine-pictures-limited",
        lifecycle=Lifecycle.OPEN,
        open_date=date(2026, 8, 18),
        close_date=date(2026, 8, 20),
    )

    assert effective_lifecycle(ipo, today=date(2026, 8, 20)) == Lifecycle.OPEN
    assert effective_lifecycle(ipo, today=date(2026, 8, 21)) == Lifecycle.CLOSED
