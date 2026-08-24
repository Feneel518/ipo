from decimal import ROUND_FLOOR, Decimal

from app.models import Ipo, IpoReservation, Segment

RESERVED_CATEGORIES = {"EMPLOYEE", "SHAREHOLDER", "MARKET_MAKER"}
LOTTERY_CATEGORIES = {"RETAIL", "INDIVIDUAL", "BNII", "SNII"}


def _whole(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _lots_at_or_below(limit: Decimal, lot_value: Decimal) -> int:
    if lot_value <= 0:
        return 0
    return _whole(limit / lot_value)


def build_lot_applications(ipo: Ipo, segment: Segment | None) -> list[dict[str, object]]:
    price = ipo.final_issue_price or ipo.price_high
    bid_lot = ipo.lot_size
    minimum = ipo.minimum_bid_quantity or bid_lot
    if price is None or bid_lot is None or minimum is None or price <= 0 or bid_lot <= 0:
        return []

    price = Decimal(price)
    lot_value = Decimal(bid_lot) * price
    minimum_lots = max(1, (minimum + bid_lot - 1) // bid_lot)

    def row(category: str, kind: str, lots: int) -> dict[str, object]:
        shares = lots * bid_lot
        return {
            "category": category,
            "application_kind": kind,
            "lots": lots,
            "shares": shares,
            "amount": Decimal(shares) * price,
        }

    if segment == Segment.SME:
        rows = [row("INDIVIDUAL", "MIN", minimum_lots)]
        # For SME issues opening from July 1, 2025, Individuals bid exactly
        # two lots and NIIs bid more than two lots. The NII book is split at
        # Rs 10 lakh in the same way as the mainboard book.
        nii_min = minimum_lots + 1
        snii_max = _lots_at_or_below(Decimal("1000000"), lot_value)
        if snii_max >= nii_min:
            rows.extend(
                [
                    row("SNII", "MIN", nii_min),
                    row("SNII", "MAX", snii_max),
                    row("BNII", "MIN", snii_max + 1),
                ]
            )
        return rows

    retail_limit = Decimal("200000")
    for rule in ipo.bid_rules:
        if rule.category == "RETAIL" and rule.maximum_subscription_amount:
            retail_limit = Decimal(rule.maximum_subscription_amount)
            break
    retail_max = _lots_at_or_below(retail_limit, lot_value)
    snii_max = _lots_at_or_below(Decimal("1000000"), lot_value)
    if retail_max < minimum_lots:
        return [row("RETAIL", "MIN", minimum_lots)]

    rows = [row("RETAIL", "MIN", minimum_lots), row("RETAIL", "MAX", retail_max)]
    if snii_max >= retail_max + 1:
        rows.extend(
            [
                row("SNII", "MIN", retail_max + 1),
                row("SNII", "MAX", snii_max),
                row("BNII", "MIN", snii_max + 1),
            ]
        )
    return rows


def _allotment_quantities(ipo: Ipo, segment: Segment | None) -> dict[str, tuple[int, int]]:
    """Return minimum bid and minimum allotment shares for lottery-style categories.

    A bNII application must exceed Rs 10 lakh, but a successful bNII is initially
    allotted the minimum NIB application size (just over Rs 2 lakh). Keeping the
    two quantities separate is also important for post-July-2025 SME issues, whose
    Individual category uses the exchange-reported two-lot minimum order.
    """
    applications = build_lot_applications(ipo, segment)
    minimum_bids = {
        str(row["category"]): int(row["shares"])
        for row in applications
        if row["application_kind"] == "MIN"
    }
    quantities: dict[str, tuple[int, int]] = {}

    if segment == Segment.SME:
        individual = minimum_bids.get("INDIVIDUAL")
        if individual:
            quantities["INDIVIDUAL"] = (individual, individual)
        minimum_nib = minimum_bids.get("SNII")
        if minimum_nib:
            quantities["SNII"] = (minimum_nib, minimum_nib)
            bnii = minimum_bids.get("BNII")
            if bnii:
                quantities["BNII"] = (bnii, minimum_nib)
        return quantities

    retail = minimum_bids.get("RETAIL")
    minimum_nib = minimum_bids.get("SNII")
    if retail:
        quantities["RETAIL"] = (retail, retail)
    if minimum_nib:
        quantities["SNII"] = (minimum_nib, minimum_nib)
        bnii = minimum_bids.get("BNII")
        if bnii:
            quantities["BNII"] = (bnii, minimum_nib)
    return quantities


def build_reservation_summary(
    ipo: Ipo, segment: Segment | None = None
) -> dict[str, object] | None:
    by_category: dict[str, IpoReservation] = {row.category: row for row in ipo.reservations}
    if not by_category:
        return None

    qib = by_category.get("QIB")
    if qib is None and by_category.get("ANCHOR") and by_category.get("QIB_EX_ANCHOR"):
        qib_shares = by_category["ANCHOR"].shares + by_category["QIB_EX_ANCHOR"].shares
    else:
        qib_shares = qib.shares if qib else Decimal(0)
    nii = by_category.get("NII")
    if nii is None:
        nii_shares = sum(
            (by_category[key].shares for key in ("BNII", "SNII") if key in by_category),
            Decimal(0),
        )
    else:
        nii_shares = nii.shares
    retail = by_category.get("RETAIL") or by_category.get("INDIVIDUAL")
    retail_shares = retail.shares if retail else Decimal(0)
    net_offer = qib_shares + nii_shares + retail_shares
    if net_offer <= 0:
        return None

    reserved = sum(
        (by_category[key].shares for key in RESERVED_CATEGORIES if key in by_category),
        Decimal(0),
    )
    reported_total = Decimal(ipo.issue_size_shares or 0)
    known_total = net_offer + reserved
    total_issue = reported_total if reported_total >= known_total else known_total

    allotment_quantities = _allotment_quantities(ipo, segment)
    rows: list[dict[str, object]] = []
    order = [
        "QIB",
        "ANCHOR",
        "QIB_EX_ANCHOR",
        "NII",
        "BNII",
        "SNII",
        "RETAIL",
        "INDIVIDUAL",
        "EMPLOYEE",
        "SHAREHOLDER",
        "MARKET_MAKER",
    ]
    for category in order:
        source = by_category.get(category)
        if source is None:
            continue
        shares = Decimal(source.shares)
        max_allottees = None
        minimum_bid_quantity = None
        minimum_allotment_quantity = None
        if category in LOTTERY_CATEGORIES and category in allotment_quantities:
            minimum_bid_quantity, minimum_allotment_quantity = allotment_quantities[category]
            max_allottees = _whole(shares / Decimal(minimum_allotment_quantity))
        rows.append(
            {
                "category": category,
                "parent_category": source.parent_category,
                "shares": shares,
                "percentage_net": (
                    shares / net_offer * Decimal(100)
                    if category in {"QIB", "NII", "RETAIL", "INDIVIDUAL"}
                    else None
                ),
                "percentage_total": shares / total_issue * Decimal(100),
                "max_allottees": max_allottees,
                "minimum_bid_quantity": minimum_bid_quantity,
                "minimum_allotment_quantity": minimum_allotment_quantity,
                "source_url": source.source_url,
                "source_type": source.source_type,
                "as_of_date": source.as_of_date,
                "is_actual": source.is_actual,
                "is_derived": source.is_derived,
            }
        )
    return {
        "total_issue_shares": total_issue,
        "net_offer_shares": net_offer,
        "reserved_shares": reserved,
        "rows": rows,
    }
