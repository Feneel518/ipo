import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.models import Lifecycle, MarketType, Segment

_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?:[Ee][+-]?\d+)?")
_LEGAL_SUFFIXES = re.compile(r"\b(limited|ltd|private|pvt|india)\b", re.I)
IST = ZoneInfo("Asia/Kolkata")


def decimal_value(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    match = _NUMBER.search(str(value))
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def integer_value(value: Any) -> int | None:
    parsed = decimal_value(value)
    return int(parsed) if parsed is not None else None


def price_band(value: Any) -> tuple[Decimal | None, Decimal | None]:
    raw = re.sub(r"(?<=\d)[-–—](?=\d)", " ", str(value or ""))
    # Exchange feeds use a hyphen as a range separator, often surrounded by
    # spaces. The generic number matcher can interpret that separator as the
    # sign of the upper price, but IPO price bands cannot be negative.
    values = [Decimal(item.replace(",", "")).copy_abs() for item in _NUMBER.findall(raw)]
    if not values:
        return None, None
    # Some BSE values append notes containing unrelated amounts, for example
    # ``92.00-97.00|Employee Discount of Rs 9|``.  The band is always the
    # first pair; using the last number mistakes the note amount for the high.
    return (values[0], values[1]) if len(values) > 1 else (values[0], values[0])


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    raw = str(value).strip()
    raw = re.sub(r"^(\d{4}-\d{2}-\d{2})T.*$", r"\1", raw)
    formats = (
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
        "%B %d, %Y",
        "%b %d, %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    for pattern in (
        r"\b\d{1,2}[- /](?:[A-Za-z]{3,9}|\d{1,2})[- /]\d{4}\b",
        r"\b[A-Za-z]{3,9} \d{1,2},? \d{4}\b",
    ):
        match = re.search(pattern, raw)
        if not match:
            continue
        candidate = match.group(0)
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


_SCHEDULE_KEYS = {
    "allotment_date": {
        "allotmentdate",
        "basisofallotmentdate",
        "basisofallotment",
        "finalisationofbasisofallotment",
        "finalizationofbasisofallotment",
        "finalisationofbasisofallotmentwiththedesignatedstockexchange",
    },
    "refund_date": {
        "refunddate",
        "initiationofrefunds",
        "initiationofrefundsorunblockingoffunds",
        "unblockingoffunds",
        "fundsunblockingdate",
    },
    "credit_date": {
        "creditdate",
        "creditofsharesdate",
        "creditofshares",
        "creditofequityshares",
        "creditofequitysharestodemataccounts",
        "demattransferdate",
    },
}


def _schedule_key(value: Any) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
    for field, aliases in _SCHEDULE_KEYS.items():
        if normalized in aliases:
            return field
    return None


def extract_schedule_dates(payload: Any) -> dict[str, date]:
    """Extract official schedule dates from known exchange key and title/value shapes."""
    found: dict[str, date] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            title_field = _schedule_key(value.get("title") or value.get("label"))
            if title_field:
                parsed = parse_date(value.get("value") or value.get("date"))
                if parsed:
                    found[title_field] = parsed
            for key, child in value.items():
                field = _schedule_key(key)
                if field:
                    parsed = parse_date(child)
                    if parsed:
                        found[field] = parsed
                if isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return found


def normalize_name(value: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    clean = _LEGAL_SUFFIXES.sub("", ascii_name.lower())
    return re.sub(r"[^a-z0-9]+", " ", clean).strip()


def segment(value: Any) -> Segment:
    raw = str(value or "").upper()
    return Segment.SME if raw in {"SM", "SME", "ST"} or "SME" in raw else Segment.MAINBOARD


def market_type(value: Any, low: Decimal | None = None, high: Decimal | None = None) -> MarketType:
    raw = str(value or "").upper()
    if "FIXED" in raw:
        return MarketType.FIXED_PRICE
    if "BOOK" in raw or (low is not None and high is not None and low != high):
        return MarketType.BOOK_BUILT
    if low is not None and high is not None and low == high:
        return MarketType.FIXED_PRICE
    return MarketType.UNKNOWN


def investor_category(value: Any) -> str:
    raw = str(value or "").upper()
    if "QUALIFIED INSTITUTIONAL" in raw or "QIB" in raw:
        return "QIB"
    if "NON-INSTITUTIONAL" in raw or "NON INSTITUTIONAL" in raw or "NIB" in raw:
        return "NIB"
    if "EMPLOYEE" in raw:
        return "EMPLOYEE"
    if "SHAREHOLDER" in raw:
        return "SHAREHOLDER"
    if "RETAIL" in raw or "INDIVIDUAL" in raw or raw == "IND":
        return "RETAIL"
    return "ALL"


def lifecycle(
    status: Any,
    open_date: date | None,
    close_date: date | None,
    listing_date: date | None,
    *,
    today: date | None = None,
) -> Lifecycle:
    current = today or datetime.now(IST).date()
    raw = str(status or "").upper()
    if "WITHDRAW" in raw:
        return Lifecycle.WITHDRAWN
    if "CANCEL" in raw or "POSTPON" in raw:
        return Lifecycle.CANCELLED
    if listing_date and listing_date <= current:
        return Lifecycle.LISTED
    if open_date and open_date > current:
        return Lifecycle.UPCOMING
    if open_date and close_date and open_date <= current <= close_date:
        return Lifecycle.OPEN
    if close_date and close_date < current:
        return Lifecycle.CLOSED
    if raw in {"ACTIVE", "L", "OPEN"}:
        return Lifecycle.OPEN
    return Lifecycle.UPCOMING
