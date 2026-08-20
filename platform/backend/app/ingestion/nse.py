import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.ingestion.http import get_json, source_client
from app.ingestion.normalize import (
    decimal_value,
    extract_schedule_dates,
    integer_value,
    investor_category,
    lifecycle,
    market_type,
    normalize_name,
    parse_date,
    price_band,
    segment,
)
from app.ingestion.types import BidRuleData, NormalizedIssue, Subscription
from app.models import Exchange, Lifecycle, MarketType

BASE = "https://www.nseindia.com"
PAGE = f"{BASE}/market-data/all-upcoming-issues-ipo"
CURRENT = f"{BASE}/api/ipo-current-issue"
UPCOMING = f"{BASE}/api/all-upcoming-issues?category=ipo"
PAST = f"{BASE}/api/public-past-issues"
DETAIL = f"{BASE}/api/ipo-detail"
ALL_EXCHANGE_CATEGORIES = f"{BASE}/api/ipo-active-category"
IST = ZoneInfo("Asia/Kolkata")


def _is_equity_issue(row: dict[str, Any]) -> bool:
    security_type = str(row.get("securityType") or row.get("series") or "").upper()
    return not any(label in security_type for label in ("DEBT", "BOND", "NCD"))


def _subscription_category(value: Any) -> str | None:
    raw = re.sub(r"\s+", " ", str(value or "").strip()).upper()
    if raw == "TOTAL":
        return "TOTAL"
    if "QUALIFIED INSTITUTIONAL" in raw or "QIB" in raw:
        return "QIB"
    if "NON INSTITUTIONAL" in raw or "NON-INSTITUTIONAL" in raw:
        if "MORE THAN TEN LAKH" in raw:
            return "BNII"
        if "UPTO TEN LAKH" in raw or "UP TO TEN LAKH" in raw:
            return "SNII"
        return "NII"
    if "RETAIL" in raw:
        return "RETAIL"
    if "EMPLOYEE" in raw:
        return "EMPLOYEE"
    if "SHAREHOLDER" in raw:
        return "SHAREHOLDER"
    return None


def _nse_updated_at(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    raw = re.sub(r"^Updated as on\s+", "", raw, flags=re.I)
    raw = re.sub(r"\s+hrs$", "", raw, flags=re.I)
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def normalize_all_exchange_subscriptions(
    payload: Any, *, source: str = ALL_EXCHANGE_CATEGORIES
) -> list[Subscription]:
    if not isinstance(payload, dict) or not isinstance(payload.get("dataList"), list):
        raise ValueError("NSE subscription contract changed: dataList is not a list")
    captured_at = _nse_updated_at(payload.get("updateTime")) or datetime.now(UTC)
    subscriptions: list[Subscription] = []
    for row in payload["dataList"]:
        if not isinstance(row, dict):
            continue
        category = _subscription_category(row.get("category"))
        reserved = decimal_value(row.get("noOfShareOffered") or row.get("noOfSharesOffered"))
        bid_quantity = decimal_value(row.get("noOfSharesBid") or row.get("noOfsharesBid"))
        if category is None or reserved is None:
            continue
        calculated = (
            bid_quantity / reserved
            if bid_quantity is not None and reserved > Decimal(0)
            else None
        )
        subscriptions.append(
            Subscription(
                category=category,
                shares_reserved_for_category=reserved,
                raw_exchange_bid_quantity=bid_quantity,
                applications=decimal_value(
                    row.get("noofapplication")
                    or row.get("noOfApplications")
                    or row.get("noOfApplication")
                ),
                calculated_subscription=calculated,
                source_reported_multiple=decimal_value(
                    row.get("noOfTotalMeant") or row.get("noOfTime")
                ),
                captured_at=captured_at,
                source=source,
                bid_data_scope="ALL_EXCHANGES",
            )
        )
    return subscriptions


class NSEAdapter:
    exchange = Exchange.NSE

    async def fetch(self, year: int) -> list[NormalizedIssue]:
        headers = {"Accept": "application/json, text/plain, */*", "Referer": PAGE}
        rows: dict[str, tuple[dict[str, Any], str]] = {}
        async with source_client() as client:
            warm = await client.get(PAGE, headers=headers)
            warm.raise_for_status()
            for endpoint in (UPCOMING, CURRENT):
                payload = await get_json(client, endpoint, headers=headers)
                if not isinstance(payload, list):
                    raise ValueError(f"NSE contract changed: {endpoint} is not a list")
                for row in payload:
                    if not _is_equity_issue(row):
                        continue
                    key = str(row.get("symbol") or row.get("companyName") or "")
                    if key:
                        previous = rows.get(key, ({}, endpoint))[0]
                        rows[key] = ({**previous, **row}, endpoint)

            start = date(year, 1, 1)
            final = date.today()
            while start <= final:
                end = min(start + timedelta(days=91), final)
                params = {
                    "from_date": start.strftime("%d-%m-%Y"),
                    "to_date": end.strftime("%d-%m-%Y"),
                }
                payload = await get_json(client, PAST, params=params, headers=headers)
                if isinstance(payload, list):
                    for row in payload:
                        if not _is_equity_issue(row):
                            continue
                        key = str(
                            row.get("symbol")
                            or row.get("companyName")
                            or row.get("company_name")
                            or ""
                        )
                        if key:
                            previous = rows.get(key, ({}, PAST))[0]
                            rows[key] = ({**previous, **row}, PAST)
                start = end + timedelta(days=1)
        return [self._normalize(key, raw, endpoint) for key, (raw, endpoint) in rows.items()]

    async def enrich(
        self, issues: list[NormalizedIssue]
    ) -> tuple[list[NormalizedIssue], dict[str, str]]:
        enriched: list[NormalizedIssue] = []
        errors: dict[str, str] = {}
        headers = {"Accept": "application/json, text/plain, */*", "Referer": PAGE}
        async with source_client() as client:
            warm = await client.get(PAGE, headers=headers)
            warm.raise_for_status()
            for issue in issues:
                if not issue.symbol:
                    errors[issue.source_id] = "NSE detail requires a symbol"
                    enriched.append(issue)
                    continue
                params = {"symbol": issue.symbol}
                if issue.series:
                    params["series"] = issue.series
                try:
                    payload = await get_json(client, DETAIL, params=params, headers=headers)
                    merged = self._merge_detail(issue, payload)
                    if issue.lifecycle == Lifecycle.OPEN:
                        try:
                            bid_payload = await get_json(
                                client,
                                ALL_EXCHANGE_CATEGORIES,
                                params={"symbol": issue.symbol},
                                headers=headers,
                            )
                            merged = merged.model_copy(
                                update={
                                    "subscriptions": normalize_all_exchange_subscriptions(
                                        bid_payload,
                                        source=(
                                            f"{ALL_EXCHANGE_CATEGORIES}?"
                                            f"{urlencode({'symbol': issue.symbol})}"
                                        ),
                                    ),
                                    "subscription_raw": bid_payload,
                                    "subscription_endpoint": ALL_EXCHANGE_CATEGORIES,
                                }
                            )
                        except Exception as exc:
                            errors[issue.source_id] = f"subscription: {exc}"
                    enriched.append(merged)
                except Exception as exc:
                    errors[issue.source_id] = str(exc)
                    enriched.append(issue)
        return enriched, errors

    def _merge_detail(self, issue: NormalizedIssue, payload: Any) -> NormalizedIssue:
        issue_info = payload.get("issueInfo", {}) if isinstance(payload, dict) else {}
        rows = issue_info.get("dataList", []) if isinstance(issue_info, dict) else []
        if not isinstance(rows, list) or not rows:
            raise ValueError("NSE detail contract changed: issueInfo.dataList is empty")
        details = {
            str(item.get("title") or "").strip(): str(item.get("value") or "").strip('" ')
            for item in rows
            if isinstance(item, dict) and item.get("title")
        }
        schedule = extract_schedule_dates(payload)
        low, high = price_band(details.get("Price Range") or details.get("Issue Price"))
        minimum = integer_value(details.get("Minimum Order Quantity"))
        rules: dict[str, BidRuleData] = {}
        for title, value in details.items():
            if title.startswith("Maximum Subscription Amount"):
                category = investor_category(title)
                rules[category] = BidRuleData(
                    category=category,
                    minimum_bid_quantity=minimum,
                    maximum_subscription_amount=decimal_value(value),
                )
            elif title.startswith("Maximum Bid Quantity"):
                category = investor_category(title)
                current = rules.get(category, BidRuleData(category=category))
                rules[category] = current.model_copy(
                    update={
                        "minimum_bid_quantity": minimum,
                        "maximum_bid_quantity": integer_value(value),
                    }
                )
        if minimum is not None and not rules:
            rules["ALL"] = BidRuleData(category="ALL", minimum_bid_quantity=minimum)
        documents = list(issue.documents)
        for title, value in details.items():
            if value.startswith("http") and any(
                label in title.upper() for label in ("PROSPECTUS", "RHP", "ANCHOR")
            ):
                documents.append((title.upper().replace(" ", "_"), title, value))
        issue_price = decimal_value(details.get("Issue Price")) or issue.final_issue_price
        detected_market_type = market_type(
            details.get("Issue Type"), low or issue.price_low, high or issue.price_high
        )
        updated = issue.model_copy(
            update={
                "series": issue.series or str(issue_info.get("series") or "") or None,
                "price_low": low or issue.price_low,
                "price_high": high or issue.price_high,
                "final_issue_price": issue_price,
                "face_value": decimal_value(details.get("Face Value")) or issue.face_value,
                "tick_size": decimal_value(details.get("Tick Size")) or issue.tick_size,
                "lot_size": integer_value(details.get("Bid Lot") or details.get("Market Lot"))
                or issue.lot_size,
                "minimum_bid_quantity": minimum or issue.minimum_bid_quantity,
                "market_type": detected_market_type
                if detected_market_type != MarketType.UNKNOWN
                else issue.market_type,
                "registrar": details.get("Name of the Registrar") or issue.registrar,
                "lead_managers": [details["Book Running Lead Managers"]]
                if details.get("Book Running Lead Managers")
                else issue.lead_managers,
                **schedule,
                **{f"{field}_is_estimated": False for field in schedule},
                "documents": documents,
                "bid_rules": list(rules.values()),
                "detail_raw": payload,
                "detail_endpoint": DETAIL,
                "detail_fetched_at": datetime.now(UTC),
            }
        )
        return updated.with_calculated_values()

    def _normalize(self, source_id: str, row: dict[str, Any], endpoint: str) -> NormalizedIssue:
        name = str(row.get("companyName") or row.get("company_name") or source_id).strip()
        opened = parse_date(
            row.get("issueStartDate") or row.get("ipoStartDate") or row.get("issue_start_date")
        )
        closed = parse_date(
            row.get("issueEndDate") or row.get("ipoEndDate") or row.get("issue_end_date")
        )
        listed = parse_date(row.get("listingDate") or row.get("listing_date"))
        schedule = extract_schedule_dates(row)
        low, high = price_band(
            row.get("issuePrice") or row.get("priceBand") or row.get("priceRange")
        )
        lifecycle_status = row.get("status") or row.get("issueStatus") or name
        offered = decimal_value(row.get("noOfSharesOffered") or row.get("issueSize"))
        bids = decimal_value(row.get("noOfSharesBid") or row.get("totalBidQuantity"))
        multiple = decimal_value(row.get("noOfTime") or row.get("subscription"))
        subscriptions = []
        if any(item is not None for item in (offered, bids, multiple)):
            subscriptions.append(
                Subscription(
                    category=str(row.get("category") or "TOTAL").upper(),
                    shares_reserved_for_category=offered,
                    raw_exchange_bid_quantity=bids,
                    calculated_subscription=(
                        bids / offered if bids is not None and offered else None
                    ),
                    source_reported_multiple=multiple,
                    source=endpoint,
                    bid_data_scope="NSE_DISCOVERY",
                )
            )
        return NormalizedIssue(
            exchange=Exchange.NSE,
            segment=segment(row.get("series") or row.get("securityType")),
            source_id=source_id,
            endpoint=endpoint,
            source_url=PAGE,
            company_name=name,
            normalized_name=normalize_name(name),
            symbol=str(row.get("symbol") or "").upper() or None,
            series=str(row.get("series") or "").upper() or None,
            source_status=str(row.get("status") or "") or None,
            isin=row.get("isin"),
            lifecycle=lifecycle(lifecycle_status, opened, closed, listed),
            open_date=opened,
            close_date=closed,
            **schedule,
            listing_date=listed,
            price_low=low,
            price_high=high,
            final_issue_price=decimal_value(row.get("finalIssuePrice")),
            face_value=decimal_value(row.get("faceValue")),
            tick_size=decimal_value(row.get("tickSize")),
            lot_size=integer_value(row.get("marketLot") or row.get("lotSize")),
            minimum_bid_quantity=integer_value(
                row.get("minimumOrderQuantity") or row.get("minimumBidQuantity")
            ),
            issue_size_shares=decimal_value(row.get("issueSize")),
            market_type=market_type(row.get("issueType"), low, high),
            issue_price=decimal_value(row.get("finalIssuePrice")),
            listing_price=decimal_value(row.get("listingOpen")),
            listing_close=decimal_value(row.get("listingClose")),
            subscriptions=subscriptions,
            raw=row,
        )
