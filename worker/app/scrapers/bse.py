import asyncio
from typing import Any

import httpx

from app.scrapers.http import BROWSER_HEADERS, exchange_client
from app.scrapers.models import Board, SourceIssue

BSE_API_BASE = "https://api.bseindia.com/BseIndiaAPI/api"
BSE_PAGE_URL = "https://www.bseindia.com/markets/PublicIssues/IPOIssues"
BSE_LIST_PATH = "/GetPublicIssue_par_updated/w?flag=1"
BSE_DETAIL_PATH = "/GetMkt_ISSUE_BBS_IPO/w"


class BSEScraper:
    """Scrape live and forthcoming BSE mainboard IPOs."""

    source_name = "bse_mainboard"
    board: Board = "mainboard"
    platform = "MAINBOARD"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        detail_concurrency: int = 4,
    ) -> None:
        self._client = client
        self._detail_concurrency = detail_concurrency

    def _matches_board(self, row: dict[str, Any]) -> bool:
        return str(row.get("eXCHANGE_PLATFORM") or "").strip().upper() == self.platform

    async def _enrich(
        self,
        client: httpx.AsyncClient,
        row: dict[str, Any],
        semaphore: asyncio.Semaphore,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        ipo_number = row.get("IPO_NO")
        if ipo_number is None:
            return row
        try:
            async with semaphore:
                response = await client.get(
                    f"{BSE_API_BASE}{BSE_DETAIL_PATH}",
                    params={"IPO_NO": ipo_number},
                    headers=headers,
                )
                response.raise_for_status()
            detail_payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {**row, "_detail_error": str(exc)}
        details = (
            detail_payload.get("IPONO_0") if isinstance(detail_payload, dict) else None
        )
        if (
            not isinstance(details, list)
            or not details
            or not isinstance(details[0], dict)
        ):
            return {**row, "_detail_error": "IPONO_0 missing from detail response"}
        return {**row, **details[0]}

    async def fetch(self) -> list[SourceIssue]:
        headers = {
            **BROWSER_HEADERS,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.bseindia.com",
            "Referer": BSE_PAGE_URL,
        }
        async with exchange_client(self._client, headers=headers) as client:
            response = await client.get(
                f"{BSE_API_BASE}{BSE_LIST_PATH}", headers=headers
            )
            response.raise_for_status()
            payload = response.json()
            raw_rows = payload.get("Table") if isinstance(payload, dict) else None
            if not isinstance(raw_rows, list):
                raise ValueError("BSE issue endpoint returned no Table list")
            rows = [
                row
                for row in raw_rows
                if isinstance(row, dict)
                and str(row.get("IR_flag") or "").strip().upper() == "IPO"
                and self._matches_board(row)
            ]
            semaphore = asyncio.Semaphore(self._detail_concurrency)
            enriched = await asyncio.gather(
                *(self._enrich(client, row, semaphore, headers) for row in rows)
            )

        issues = []
        for row in enriched:
            source_id = str(row.get("IPO_NO") or row.get("Scrip_cd") or "")
            issues.append(
                SourceIssue(
                    source=self.source_name,
                    exchange="BSE",
                    board=self.board,
                    source_id=source_id,
                    payload=row,
                )
            )
        return issues


class BSESMEScraper(BSEScraper):
    """Scrape BSE SME issues from the official public-issue feed."""

    source_name = "bse_sme"
    board: Board = "SME"
    platform = "SME"
