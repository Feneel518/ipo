import re
from typing import Any

import httpx

from app.scrapers.http import BROWSER_HEADERS, exchange_client
from app.scrapers.models import Board, SourceIssue

NSE_BASE_URL = "https://www.nseindia.com"
NSE_WARM_PATH = "/market-data/all-upcoming-issues-ipo"
NSE_UPCOMING_PATH = "/api/all-upcoming-issues?category=ipo"
NSE_CURRENT_PATH = "/api/ipo-current-issue"
NSE_DETAIL_PATH = "/api/ipo-detail"

_SHARE_COUNT = re.compile(r"([\d,]+)\s+equity shares", re.IGNORECASE)
_FRESH_SHARES = re.compile(
    r"fresh issue\s+(?:of\s+)?(?:up to\s+)?([\d,]+)\s+equity shares",
    re.IGNORECASE,
)
_OFS_SHARES = re.compile(
    r"offer for sale\s+(?:of\s+)?(?:up to\s+)?([\d,]+)\s+equity shares",
    re.IGNORECASE,
)


class NSEScraper:
    """Scrape current and forthcoming NSE mainboard IPOs."""

    source_name = "nse_mainboard"
    board: Board = "mainboard"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def _matches_board(self, row: dict[str, Any]) -> bool:
        series = str(row.get("series") or "").strip().upper()
        return series in {"EQ", "BE"}

    @staticmethod
    def _issue_share_count(value: str) -> str | None:
        fresh = _FRESH_SHARES.search(value)
        ofs = _OFS_SHARES.search(value)
        if fresh or ofs:
            total = sum(
                int(match.group(1).replace(",", ""))
                for match in (fresh, ofs)
                if match is not None
            )
            return str(total) if total > 0 else None
        match = _SHARE_COUNT.search(value)
        return match.group(1).replace(",", "") if match else None

    async def _enrich_incomplete_row(
        self,
        client: httpx.AsyncClient,
        row: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        if row.get("issuePrice") and row.get("issueSize"):
            return row
        symbol = row.get("symbol")
        series = row.get("series")
        if not symbol or not series:
            return row
        try:
            response = await client.get(
                f"{NSE_BASE_URL}{NSE_DETAIL_PATH}",
                params={"symbol": symbol, "series": series},
                headers=headers,
            )
            response.raise_for_status()
            detail = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {**row, "_detail_error": str(exc)}
        issue_info = detail.get("issueInfo") if isinstance(detail, dict) else None
        data_list = issue_info.get("dataList") if isinstance(issue_info, dict) else None
        if not isinstance(data_list, list):
            return {**row, "_detail_error": "issueInfo.dataList missing"}
        fields = {
            str(item.get("title") or "").strip(): item.get("value")
            for item in data_list
            if isinstance(item, dict) and item.get("title")
        }
        issue_size = self._issue_share_count(str(fields.get("Issue Size") or ""))
        lot_match = re.search(r"\d[\d,]*", str(fields.get("Lot Size") or ""))
        return {
            **row,
            "companyName": issue_info.get("heading") or row.get("companyName"),
            "issuePrice": fields.get("Price Range") or row.get("issuePrice"),
            "issueSize": issue_size or row.get("issueSize"),
            "Market_Lot": (lot_match.group(0).replace(",", "") if lot_match else None),
            "Registrar": fields.get("Name of the Registrar"),
            "Prospectus_GID": fields.get("Red Herring Prospectus"),
        }

    async def fetch(self) -> list[SourceIssue]:
        headers = {
            **BROWSER_HEADERS,
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{NSE_BASE_URL}{NSE_WARM_PATH}",
        }
        async with exchange_client(self._client, headers=headers) as client:
            # NSE's API commonly returns 401/403 to a cold client.  Visiting the
            # market page first establishes the cookies expected by the API.
            warm_response = await client.get(
                f"{NSE_BASE_URL}{NSE_WARM_PATH}", headers=headers
            )
            warm_response.raise_for_status()

            rows: dict[str, dict[str, Any]] = {}
            for path in (NSE_UPCOMING_PATH, NSE_CURRENT_PATH):
                response = await client.get(f"{NSE_BASE_URL}{path}", headers=headers)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError(f"NSE endpoint {path} returned a non-list payload")
                for row in payload:
                    if not isinstance(row, dict) or not self._matches_board(row):
                        continue
                    source_id = str(row.get("symbol") or row.get("companyName") or "")
                    if source_id:
                        # Current data contains subscription fields absent from
                        # the forthcoming endpoint, so let it enrich the row.
                        rows[source_id] = {**rows.get(source_id, {}), **row}

            for source_id, row in list(rows.items()):
                rows[source_id] = await self._enrich_incomplete_row(
                    client, row, headers
                )

        return [
            SourceIssue(
                source=self.source_name,
                exchange="NSE",
                board=self.board,
                source_id=source_id,
                payload=row,
            )
            for source_id, row in rows.items()
        ]


class NSEEmergeScraper(NSEScraper):
    """Scrape NSE Emerge (SME) issues from the official IPO feeds."""

    source_name = "nse_emerge"
    board: Board = "SME"

    def _matches_board(self, row: dict[str, Any]) -> bool:
        security_type = (
            str(row.get("series") or row.get("securityType") or "").strip().upper()
        )
        return security_type in {"SM", "SME", "ST"}
