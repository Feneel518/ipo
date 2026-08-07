import logging
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.scrapers.models import (
    IPOStatus,
    NormalizationResult,
    NormalizedIPO,
    RejectedIssue,
    SourceIssue,
)

logger = logging.getLogger(__name__)

_EMPTY = {None, "", "-", "--", "N/A", "NA", "null"}
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


class IPONormalizer:
    """Normalize all exchange payloads and merge by exchange + symbol."""

    def __init__(self, *, today: date | None = None) -> None:
        self.today = today or date.today()

    def _failed(self, issue: SourceIssue, field: str, value: Any, reason: str) -> None:
        logger.warning(
            "unparsed field source=%s source_id=%s field=%s value=%r reason=%s",
            issue.source,
            issue.source_id,
            field,
            value,
            reason,
        )

    @staticmethod
    def _first(payload: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = payload.get(key)
            if value is not None and (
                not isinstance(value, str) or value.strip() not in _EMPTY
            ):
                return value
        return None

    def _required_text(self, issue: SourceIssue, field: str, *keys: str) -> str | None:
        value = self._first(issue.payload, *keys)
        if value is None:
            self._failed(issue, field, None, "field is missing")
            return None
        parsed = " ".join(str(value).split()).strip()
        if not parsed:
            self._failed(issue, field, value, "value is blank")
            return None
        return parsed

    def _date(self, issue: SourceIssue, field: str, *keys: str) -> date | None:
        value = self._first(issue.payload, *keys)
        if value is None:
            self._failed(issue, field, None, "field is missing")
            return None
        text = str(value).strip()
        iso_text = text[:10]
        formats = (
            "%Y-%m-%d",
            "%d-%b-%Y",
            "%d %b %Y",
            "%d/%m/%Y",
        )
        for candidate in (iso_text, text):
            for fmt in formats:
                try:
                    return datetime.strptime(candidate, fmt).date()
                except ValueError:
                    pass
        self._failed(issue, field, value, "unsupported date format")
        return None

    def _price_band(self, issue: SourceIssue) -> tuple[Decimal | None, Decimal | None]:
        value = self._first(issue.payload, "issuePrice", "Price_Band")
        if value is None:
            self._failed(issue, "price_band", None, "field is missing")
            return None, None
        try:
            numbers = [Decimal(number) for number in _NUMBER.findall(str(value))]
        except InvalidOperation:
            numbers = []
        if not numbers:
            self._failed(issue, "price_band", value, "no numeric price found")
            return None, None
        if len(numbers) == 1:
            return numbers[0], numbers[0]
        return min(numbers[0], numbers[1]), max(numbers[0], numbers[1])

    def _positive_int(self, issue: SourceIssue, field: str, *keys: str) -> int | None:
        value = self._first(issue.payload, *keys)
        if value is None:
            self._failed(issue, field, None, "field is missing")
            return None
        try:
            parsed = int(Decimal(str(value).replace(",", "")))
        except (InvalidOperation, ValueError):
            self._failed(issue, field, value, "not an integer")
            return None
        if parsed <= 0:
            self._failed(issue, field, value, "must be positive")
            return None
        return parsed

    def _status(
        self,
        issue: SourceIssue,
        open_date: date | None,
        close_date: date | None,
        listing_date: date | None,
    ) -> IPOStatus:
        raw = str(self._first(issue.payload, "status", "Status") or "").upper()
        if raw == "LISTED" or (listing_date and listing_date <= self.today):
            return "listed"
        if raw in {"F", "FORTHCOMING", "UPCOMING"}:
            return "upcoming"
        if raw in {"L", "ACTIVE", "OPEN", "LIVE"}:
            if close_date and close_date < self.today:
                return "closed"
            if open_date and open_date > self.today:
                return "upcoming"
            return "open"
        self._failed(issue, "status", raw or None, "unknown issue status")
        if close_date and close_date < self.today:
            return "closed"
        return "upcoming" if open_date and open_date > self.today else "open"

    def _optional_text(self, issue: SourceIssue, field: str, *keys: str) -> str | None:
        value = self._first(issue.payload, *keys)
        if value is None:
            self._failed(issue, field, None, "field is missing")
            return None
        return " ".join(str(value).split()).strip() or None

    def normalize_one(self, issue: SourceIssue) -> NormalizedIPO | None:
        name = self._required_text(
            issue, "name", "companyName", "company", "ScripName", "Scrip_Name"
        )
        symbol = self._required_text(issue, "symbol", "symbol", "Symbol", "short_name")
        if not name or not symbol:
            return None
        symbol = re.sub(r"\s+", "", symbol).upper()
        exchange_security_code = self._first(
            issue.payload, "exchange_security_code", "Scrip_cd", "ScripCode"
        )
        if exchange_security_code is not None:
            exchange_security_code = str(exchange_security_code).strip().upper() or None
        open_date = self._date(issue, "open_date", "issueStartDate", "Start_Dt")
        close_date = self._date(issue, "close_date", "issueEndDate", "End_Dt")
        allotment_date = self._date(
            issue, "allotment_date", "allotmentDate", "Allotment_Date"
        )
        refund_date = self._date(issue, "refund_date", "refundDate", "Refund_Date")
        listing_date = self._date(issue, "listing_date", "listingDate", "Listing_Date")
        low, high = self._price_band(issue)
        lot_size = self._positive_int(issue, "lot_size", "Market_Lot")
        shares = self._positive_int(
            issue, "issue_size_shares", "issueSize", "Issue_Size_No_of_shares"
        )
        issue_size = None
        if shares is not None and high is not None:
            issue_size = (Decimal(shares) * high / Decimal("10000000")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            self._failed(
                issue,
                "issue_size",
                {"shares": shares, "price_band_high": high},
                "requires share count and upper price",
            )

        registrar = self._optional_text(issue, "registrar", "Registrar")
        if registrar:
            registrar = registrar.split("^", 1)[0].strip()
        drhp_link = self._optional_text(
            issue, "drhp_link", "Prospectus_GID", "drhpLink", "rhpLink"
        )
        if drhp_link and not drhp_link.lower().startswith(("http://", "https://")):
            self._failed(issue, "drhp_link", drhp_link, "not an absolute HTTP URL")
            drhp_link = None

        return NormalizedIPO(
            name=name,
            symbol=symbol,
            exchange=issue.exchange,
            exchange_security_code=exchange_security_code,
            board=issue.board,
            status=self._status(issue, open_date, close_date, listing_date),
            price_band_low=low,
            price_band_high=high,
            lot_size=lot_size,
            issue_size=issue_size,
            open_date=open_date,
            close_date=close_date,
            allotment_date=allotment_date,
            refund_date=refund_date,
            listing_date=listing_date,
            registrar=registrar,
            drhp_link=drhp_link,
            sources=[issue.source],
        )

    def merge(self, issues: list[SourceIssue]) -> NormalizationResult:
        merged: dict[tuple[str, str], NormalizedIPO] = {}
        rejected: list[RejectedIssue] = []
        for issue in issues:
            normalized = self.normalize_one(issue)
            if normalized is None:
                reason = "required name or symbol could not be parsed"
                logger.error(
                    "rejected issue source=%s source_id=%s reason=%s",
                    issue.source,
                    issue.source_id,
                    reason,
                )
                rejected.append(
                    RejectedIssue(issue.source, issue.source_id, reason, issue.payload)
                )
                continue
            key = (normalized.exchange, normalized.symbol)
            existing = merged.get(key)
            if existing is None:
                merged[key] = normalized
                continue
            self._merge_record(existing, normalized)
        return NormalizationResult(list(merged.values()), rejected)

    def _merge_record(self, target: NormalizedIPO, incoming: NormalizedIPO) -> None:
        for field in (
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
            "drhp_link",
            "exchange_security_code",
        ):
            old = getattr(target, field)
            new = getattr(incoming, field)
            if old is None and new is not None:
                setattr(target, field, new)
            elif old is not None and new is not None and old != new:
                logger.warning(
                    "merge conflict exchange=%s symbol=%s field=%s kept=%r ignored=%r",
                    target.exchange,
                    target.symbol,
                    field,
                    old,
                    new,
                )
        for source in incoming.sources:
            if source not in target.sources:
                target.sources.append(source)
