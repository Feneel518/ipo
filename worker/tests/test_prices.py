import asyncio
import io
import zipfile
from datetime import date
from decimal import Decimal

import httpx

from app.prices.bhavcopy import BhavcopyClient, BhavcopyUnavailable, parse_bhavcopy
from app.prices.history import NSEPastIssueScraper, scrape_past_ipos
from app.prices.models import Bhavcopy, EODPrice, IPOSecurity
from app.prices.service import PriceIngestionService


def _zip(name: str, contents: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(name, contents)
    return output.getvalue()


def test_parse_legacy_nse_and_bse_bhavcopies() -> None:
    day = date(2023, 8, 7)
    nse = parse_bhavcopy(
        b"SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE\nIPOONE,EQ,101,110,99,108\n",
        "NSE",
        day,
    )
    bse = parse_bhavcopy(
        b"SC_CODE,SC_NAME,OPEN,HIGH,LOW,CLOSE\n543999,IPO LTD,52,61,50,59\n",
        "BSE",
        day,
    )

    assert nse.find("ipoone", None) == EODPrice(
        "IPOONE", None, Decimal("101"), Decimal("108")
    )
    assert bse.find("IGNORED", "543999") == EODPrice(
        None, "543999", Decimal("52"), Decimal("59")
    )


def test_parse_udiff_filters_non_stocks_and_cleans_bse_marker() -> None:
    payload = (
        b"TradDt,FinInstrmTp,FinInstrmId,TckrSymb,OpnPric,ClsPric\n"
        b"2025-08-07,STK,544000,NEWIPO#,100,112\n"
        b"2025-08-07,ETF,999999,NOTIPO,10,11\n"
    )
    result = parse_bhavcopy(payload, "BSE", date(2025, 8, 7))

    assert result.find("NEWIPO", None) is not None
    assert result.find("NOTIPO", None) is None
    assert result.find("anything", "544000") is not None


def test_client_handles_zip_and_html_missing_page() -> None:
    csv_bytes = b"SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE\nIPOONE,EQ,101,110,99,108\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if "20230807" in str(request.url) or "07AUG2023" in str(request.url):
            return httpx.Response(200, content=_zip("prices.csv", csv_bytes))
        return httpx.Response(200, text="<html>file unavailable</html>")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            source = BhavcopyClient(client)
            result = await source.fetch("NSE", date(2023, 8, 7))
            assert result.find("IPOONE", None) is not None
            try:
                await source.fetch("BSE", date(2025, 8, 9))
            except BhavcopyUnavailable:
                pass
            else:
                raise AssertionError("HTML missing page should be unavailable")

    asyncio.run(run())


def test_past_issue_feed_normalizes_a_listed_sme_ipo() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("all-upcoming-issues-ipo"):
            return httpx.Response(200, text="warm")
        assert request.url.params["from_date"] == "01-08-2023"
        return httpx.Response(
            200,
            json=[
                {
                    "company": "Past Limited",
                    "symbol": "PAST",
                    "ipoStartDate": "01-AUG-2023",
                    "ipoEndDate": "03-AUG-2023",
                    "listingDate": "07-AUG-2023",
                    "priceRange": "Rs. 95 to Rs. 100",
                    "securityType": "SME",
                },
                {
                    "company": "Not An IPO Bond",
                    "symbol": "900BOND28",
                    "securityType": "N0",
                },
                {
                    "company": "Existing Limited - FPO",
                    "symbol": "EXISTFPO",
                    "securityType": "EQ",
                },
            ],
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            scraper = NSEPastIssueScraper(client)
            return await scrape_past_ipos(
                date(2023, 8, 1), date(2023, 8, 31), scraper=scraper
            )

    result = asyncio.run(run())
    assert not result.rejected
    assert result.ipos[0].status == "listed"
    assert result.ipos[0].board == "SME"
    assert result.ipos[0].listing_date == date(2023, 8, 7)
    assert len(result.ipos) == 1


class FakeRepository:
    def __init__(self) -> None:
        self.ipo = IPOSecurity(1, "NEWIPO", "NSE", None, date(2025, 8, 7))
        self.listing_values = []
        self.current_values = []

    def listed_ipos(self, start: date, end: date):
        return [self.ipo] if start <= self.ipo.listing_date <= end else []

    def listed_ipos_missing_prices(self, start: date, end: date):
        return self.listed_ipos(start, end)

    def all_listed_ipos(self, as_of: date):
        return [self.ipo] if self.ipo.listing_date <= as_of else []

    def update_listing_prices(self, values):
        self.listing_values = list(values)
        return len(self.listing_values)

    def update_current_prices(self, values):
        self.current_values = list(values)
        return len(self.current_values)


class FakeClient:
    async def fetch(self, exchange: str, day: date) -> Bhavcopy:
        if day.weekday() >= 5:
            raise BhavcopyUnavailable
        price = EODPrice("NEWIPO", None, Decimal("100"), Decimal("110"))
        return Bhavcopy("NSE", day, {"NEWIPO": price}, {})


def test_backfill_sets_listing_price_and_falls_back_for_current_price() -> None:
    repository = FakeRepository()
    service = PriceIngestionService(repository, FakeClient())  # type: ignore[arg-type]
    result = asyncio.run(service.backfill(date(2025, 8, 7), date(2025, 8, 10)))

    assert result.listing_prices_updated == 1
    assert result.current_prices_updated == 1
    assert result.current_price_date == date(2025, 8, 8)
    assert repository.listing_values[0][2] == date(2025, 8, 7)
    assert repository.current_values[0][2] == date(2025, 8, 8)
