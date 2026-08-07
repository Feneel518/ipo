from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

Board = Literal["mainboard", "SME"]
IPOStatus = Literal["upcoming", "open", "closed", "allotted", "listed"]


@dataclass(frozen=True, slots=True)
class SourceIssue:
    """One issue as returned by an exchange adapter."""

    source: str
    exchange: Literal["NSE", "BSE"]
    board: Board
    source_id: str
    payload: dict[str, Any]


@dataclass(slots=True)
class NormalizedIPO:
    """Shape accepted by the database ``ipos`` write contract."""

    name: str
    symbol: str
    exchange: Literal["NSE", "BSE"]
    board: Board
    status: IPOStatus
    exchange_security_code: str | None = None
    price_band_low: Decimal | None = None
    price_band_high: Decimal | None = None
    lot_size: int | None = None
    issue_size: Decimal | None = None
    open_date: date | None = None
    close_date: date | None = None
    allotment_date: date | None = None
    refund_date: date | None = None
    listing_date: date | None = None
    registrar: str | None = None
    drhp_link: str | None = None
    sources: list[str] = field(default_factory=list)

    def as_upsert_values(self) -> dict[str, Any]:
        """Return only columns present in the ``ipos`` table."""

        values = {
            field_name: getattr(self, field_name)
            for field_name in (
                "name",
                "symbol",
                "exchange",
                "exchange_security_code",
                "board",
                "price_band_low",
                "price_band_high",
                "lot_size",
                "issue_size",
                "open_date",
                "close_date",
                "allotment_date",
                "refund_date",
                "listing_date",
                "registrar",
                "status",
                "drhp_link",
            )
        }
        return values


@dataclass(slots=True)
class RejectedIssue:
    source: str
    source_id: str
    reason: str
    payload: dict[str, Any]


@dataclass(slots=True)
class NormalizationResult:
    ipos: list[NormalizedIPO]
    rejected: list[RejectedIssue]
