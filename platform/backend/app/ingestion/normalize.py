import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models import Lifecycle, MarketType, Segment

_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?:[Ee][+-]?\d+)?")
_LEGAL_SUFFIXES = re.compile(r"\b(limited|ltd|private|pvt|india)\b", re.I)


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
    raw = str(value).split("T")[0].strip()
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


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
    current = today or date.today()
    raw = str(status or "").upper()
    if "WITHDRAW" in raw:
        return Lifecycle.WITHDRAWN
    if "CANCEL" in raw:
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
