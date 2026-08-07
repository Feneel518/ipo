import asyncio
import logging
from collections import defaultdict
from datetime import date, timedelta

from app.prices.bhavcopy import BhavcopyClient, BhavcopyUnavailable
from app.prices.models import Bhavcopy, Exchange, IngestionResult, IPOSecurity
from app.prices.repository import PriceRepository

logger = logging.getLogger(__name__)


class PriceIngestionService:
    def __init__(
        self,
        repository: PriceRepository,
        client: BhavcopyClient | None = None,
        *,
        download_concurrency: int = 6,
    ) -> None:
        self.repository = repository
        self.client = client or BhavcopyClient()
        self.download_concurrency = download_concurrency

    async def _fetch_many(
        self, keys: set[tuple[Exchange, date]]
    ) -> tuple[dict[tuple[Exchange, date], Bhavcopy], int]:
        semaphore = asyncio.Semaphore(self.download_concurrency)

        async def fetch(exchange: Exchange, day: date):
            async with semaphore:
                try:
                    return (exchange, day), await self.client.fetch(exchange, day)
                except BhavcopyUnavailable:
                    logger.info(
                        "bhavcopy unavailable exchange=%s date=%s", exchange, day
                    )
                    return (exchange, day), None

        results = await asyncio.gather(*(fetch(*key) for key in sorted(keys)))
        available = {key: copy for key, copy in results if copy is not None}
        return available, len(results) - len(available)

    async def _latest_copies(
        self, as_of: date, exchanges: set[Exchange], lookback_days: int = 7
    ) -> tuple[dict[Exchange, Bhavcopy], int]:
        copies: dict[Exchange, Bhavcopy] = {}
        unavailable = 0
        for offset in range(lookback_days + 1):
            day = as_of - timedelta(days=offset)
            missing = exchanges - copies.keys()
            if not missing:
                break
            fetched, missed = await self._fetch_many(
                {(exchange, day) for exchange in missing}
            )
            unavailable += missed
            for (exchange, _), copy in fetched.items():
                copies[exchange] = copy
        return copies, unavailable

    async def backfill(self, start: date, end: date) -> IngestionResult:
        ipos = await asyncio.to_thread(
            self.repository.listed_ipos_missing_prices, start, end
        )
        grouped: dict[tuple[Exchange, date], list[IPOSecurity]] = defaultdict(list)
        for ipo in ipos:
            grouped[(ipo.exchange, ipo.listing_date)].append(ipo)
        copies, unavailable = await self._fetch_many(set(grouped))

        listing_values = []
        unmatched = 0
        for key, issues in grouped.items():
            copy = copies.get(key)
            if copy is None:
                unmatched += len(issues)
                continue
            for ipo in issues:
                price = copy.find(ipo.symbol, ipo.exchange_security_code)
                if price is None:
                    unmatched += 1
                else:
                    listing_values.append((ipo, price, copy.trade_date))
        listing_count = await asyncio.to_thread(
            self.repository.update_listing_prices, listing_values
        )

        all_ipos = await asyncio.to_thread(self.repository.all_listed_ipos, end)
        exchanges = {ipo.exchange for ipo in all_ipos}
        latest, latest_unavailable = await self._latest_copies(end, exchanges)
        current_values = []
        for ipo in all_ipos:
            copy = latest.get(ipo.exchange)
            price = copy.find(ipo.symbol, ipo.exchange_security_code) if copy else None
            if price:
                current_values.append((ipo, price, copy.trade_date))
        current_count = await asyncio.to_thread(
            self.repository.update_current_prices, current_values
        )
        current_date = max((copy.trade_date for copy in latest.values()), default=None)
        return IngestionResult(
            len(copies) + len(latest),
            unavailable + latest_unavailable,
            listing_count,
            current_count,
            unmatched,
            current_date,
        )

    async def daily(self, as_of: date) -> IngestionResult:
        # Reusing backfill for one date makes retries idempotent and also captures
        # the listing-day open/close for IPOs debuting on this trading day.
        return await self.backfill(as_of, as_of)
