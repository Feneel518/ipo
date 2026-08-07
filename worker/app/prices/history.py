from datetime import date
from typing import Any

import httpx

from app.scrapers.http import BROWSER_HEADERS, exchange_client
from app.scrapers.models import NormalizationResult, SourceIssue
from app.scrapers.normalizer import IPONormalizer

NSE_BASE_URL = "https://www.nseindia.com"
NSE_IPO_PAGE = "/market-data/all-upcoming-issues-ipo"
NSE_PAST_ISSUES = "/api/public-past-issues"

# Offer-stage symbols that differ from the official listing-day NSE ticker.
_TRADING_SYMBOL_OVERRIDES = {
    "ROCKPP": "ROCKINGDCE",
    "SAATVIK": "SAATVIKGL",
}


class NSEPastIssueScraper:
    """Read the official past-issues feed that backs NSE's IPO page."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch(self, start: date, end: date) -> list[SourceIssue]:
        headers = {
            **BROWSER_HEADERS,
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{NSE_BASE_URL}{NSE_IPO_PAGE}",
        }
        params = {
            "from_date": start.strftime("%d-%m-%Y"),
            "to_date": end.strftime("%d-%m-%Y"),
        }
        async with exchange_client(self._client, headers=headers) as client:
            warm = await client.get(f"{NSE_BASE_URL}{NSE_IPO_PAGE}", headers=headers)
            warm.raise_for_status()
            response = await client.get(
                f"{NSE_BASE_URL}{NSE_PAST_ISSUES}",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("NSE past-issues endpoint returned a non-list payload")

        issues = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip()
            if not symbol or symbol[0].isdigit():
                continue
            symbol = _TRADING_SYMBOL_OVERRIDES.get(symbol.upper(), symbol)
            security_type = str(row.get("securityType") or "").strip().upper()
            company_name = str(
                row.get("companyName") or row.get("company") or ""
            ).strip()
            # The endpoint is a public-issues feed, not an IPO-only feed. It also
            # contains debt series, rights, InvITs, and follow-on offerings.
            if security_type not in {"EQ", "BE", "SME", "SM", "ST"}:
                continue
            if "FPO" in company_name.upper():
                continue
            board = "SME" if security_type in {"SME", "SM", "ST"} else "mainboard"
            price_range = row.get("priceRange")
            if str(price_range or "").strip() in {"", "-", "--"}:
                price_range = row.get("issuePrice")
            normalized_payload: dict[str, Any] = {
                **row,
                "symbol": symbol,
                "issueStartDate": row.get("ipoStartDate"),
                "issueEndDate": row.get("ipoEndDate"),
                "issuePrice": price_range,
                "listingDate": row.get("listingDate"),
                "status": "listed",
            }
            issues.append(
                SourceIssue(
                    source="nse_past_issues",
                    exchange="NSE",
                    board=board,
                    source_id=symbol,
                    payload=normalized_payload,
                )
            )
        return issues


async def scrape_past_ipos(
    start: date,
    end: date,
    *,
    scraper: NSEPastIssueScraper | None = None,
) -> NormalizationResult:
    issues = await (scraper or NSEPastIssueScraper()).fetch(start, end)
    return IPONormalizer(today=end).merge(issues)
