from decimal import Decimal

from app.ingestion.nse import _anchor_reservation
from app.models import BidRule, Exchange, Ipo, IpoReservation, Lifecycle, Segment
from app.offer_math import build_lot_applications, build_reservation_summary


def reservation(category: str, shares: str, parent: str | None = None) -> IpoReservation:
    return IpoReservation(
        category=category,
        parent_category=parent,
        shares=Decimal(shares),
        source_url="https://example.test/official",
        source_type="EXCHANGE_CATEGORY",
        is_actual=True,
        is_derived=False,
    )


def augmont_style_ipo() -> Ipo:
    ipo = Ipo(
        company_name="Example Limited",
        normalized_name="example",
        slug="example",
        lifecycle=Lifecycle.OPEN,
        price_high=Decimal("788"),
        lot_size=19,
        minimum_bid_quantity=19,
        issue_size_shares=Decimal("10469541"),
    )
    ipo.bid_rules = [
        BidRule(
            exchange=Exchange.NSE,
            category="RETAIL",
            minimum_bid_quantity=19,
            maximum_subscription_amount=Decimal("200000"),
        )
    ]
    ipo.reservations = [
        reservation("QIB", "5209390"),
        reservation("ANCHOR", "3125633", "QIB"),
        reservation("QIB_EX_ANCHOR", "2083757", "QIB"),
        reservation("NII", "1562817"),
        reservation("BNII", "1041878", "NII"),
        reservation("SNII", "520939", "NII"),
        reservation("RETAIL", "3646575"),
        reservation("EMPLOYEE", "50759"),
    ]
    return ipo


def test_mainboard_lot_applications_match_thresholds():
    rows = build_lot_applications(augmont_style_ipo(), Segment.MAINBOARD)

    assert [(row["category"], row["application_kind"], row["lots"]) for row in rows] == [
        ("RETAIL", "MIN", 1),
        ("RETAIL", "MAX", 13),
        ("SNII", "MIN", 14),
        ("SNII", "MAX", 66),
        ("BNII", "MIN", 67),
    ]
    assert rows[-1]["shares"] == 1273
    assert rows[-1]["amount"] == Decimal("1003124")


def test_sme_uses_exchange_minimum_order_and_post_2025_nii_buckets():
    ipo = augmont_style_ipo()
    ipo.lot_size = 2000
    ipo.minimum_bid_quantity = 4000
    ipo.price_high = Decimal("60")

    rows = build_lot_applications(ipo, Segment.SME)

    assert [(row["category"], row["application_kind"], row["lots"]) for row in rows] == [
        ("INDIVIDUAL", "MIN", 2),
        ("SNII", "MIN", 3),
        ("SNII", "MAX", 8),
        ("BNII", "MIN", 9),
    ]
    assert rows[0]["amount"] == Decimal("240000")


def test_reservation_summary_computes_totals_percentages_and_allottees():
    summary = build_reservation_summary(augmont_style_ipo(), Segment.MAINBOARD)
    assert summary is not None
    assert summary["net_offer_shares"] == Decimal("10418782")
    assert summary["total_issue_shares"] == Decimal("10469541")
    assert summary["reserved_shares"] == Decimal("50759")
    rows = {row["category"]: row for row in summary["rows"]}
    assert rows["QIB"]["percentage_net"].quantize(Decimal("0.01")) == Decimal("50.00")
    assert rows["EMPLOYEE"]["percentage_net"] is None
    assert rows["RETAIL"]["max_allottees"] == 191925
    assert rows["SNII"]["max_allottees"] == 1958
    assert rows["BNII"]["max_allottees"] == 3916
    assert rows["BNII"]["minimum_bid_quantity"] == 1273
    assert rows["BNII"]["minimum_allotment_quantity"] == 266


def test_sme_reservation_uses_exchange_reported_minimum_order():
    ipo = augmont_style_ipo()
    ipo.lot_size = 2000
    ipo.minimum_bid_quantity = 4000
    ipo.price_high = Decimal("60")
    ipo.reservations = [
        reservation("INDIVIDUAL", "120000"),
        reservation("SNII", "60000", "NII"),
        reservation("BNII", "120000", "NII"),
    ]

    summary = build_reservation_summary(ipo, Segment.SME)

    assert summary is not None
    rows = {row["category"]: row for row in summary["rows"]}
    assert rows["INDIVIDUAL"]["minimum_bid_quantity"] == 4000
    assert rows["INDIVIDUAL"]["minimum_allotment_quantity"] == 4000
    assert rows["INDIVIDUAL"]["max_allottees"] == 30
    assert rows["SNII"]["minimum_bid_quantity"] == 6000
    assert rows["SNII"]["minimum_allotment_quantity"] == 6000
    assert rows["SNII"]["max_allottees"] == 10
    assert rows["BNII"]["minimum_bid_quantity"] == 18000
    assert rows["BNII"]["minimum_allotment_quantity"] == 6000
    assert rows["BNII"]["max_allottees"] == 20


def test_anchor_shares_are_extracted_from_nse_issue_details():
    result = _anchor_reservation(
        {
            "Issue Size": (
                "Fresh Issue aggregating up to Rs. 6,200 million "
                "and Anchor reservation portion of 31,25,633 Equity shares"
            ),
            "Anchor Allocation Report": "https://example.test/anchor.zip",
        }
    )

    assert result is not None
    assert result.shares == Decimal("3125633")
    assert result.parent_category == "QIB"
    assert result.source_url == "https://example.test/anchor.zip"
