from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.scrapers.http import BROWSER_HEADERS, exchange_client
from app.scrapers.nse import NSE_BASE_URL, NSE_CURRENT_PATH, NSE_WARM_PATH


@dataclass(frozen=True, slots=True)
class SubscriptionObservation:
    symbol: str
    category: str
    multiple: Decimal


class NSESubscriptionScraper:
    """Read total subscription multiples from NSE's active-issue feed."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @staticmethod
    def _observation(row: dict[str, Any]) -> SubscriptionObservation | None:
        symbol = str(row.get("symbol") or "").strip().upper()
        value = row.get("noOfTime")
        if not symbol or value in (None, ""):
            return None
        try:
            multiple = Decimal(str(value))
        except InvalidOperation:
            return None
        if not multiple.is_finite() or multiple < 0:
            return None
        return SubscriptionObservation(symbol, "total", multiple)

    async def fetch(self, symbols: set[str]) -> list[SubscriptionObservation]:
        if not symbols:
            return []
        headers = {
            **BROWSER_HEADERS,
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{NSE_BASE_URL}{NSE_WARM_PATH}",
        }
        async with exchange_client(self._client, headers=headers) as client:
            warm = await client.get(f"{NSE_BASE_URL}{NSE_WARM_PATH}")
            warm.raise_for_status()
            response = await client.get(f"{NSE_BASE_URL}{NSE_CURRENT_PATH}")
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("NSE active-issue endpoint returned a non-list payload")
        wanted = {symbol.upper() for symbol in symbols}
        observations = (
            self._observation(row) for row in payload if isinstance(row, dict)
        )
        return [item for item in observations if item and item.symbol in wanted]
