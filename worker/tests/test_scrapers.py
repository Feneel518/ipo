import asyncio
import logging
from datetime import date
from decimal import Decimal

import httpx

from app.scrapers.bse import BSEScraper, BSESMEScraper
from app.scrapers.models import SourceIssue
from app.scrapers.normalizer import IPONormalizer
from app.scrapers.nse import NSEEmergeScraper, NSEScraper


def test_nse_warms_session_and_splits_mainboard_from_emerge() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/market-data/all-upcoming-issues-ipo":
            return httpx.Response(
                200, headers={"set-cookie": "nse-cookie=ok; Path=/"}, text="ok"
            )
        assert request.headers["user-agent"].startswith("Mozilla/5.0")
        assert request.headers["cookie"] == "nse-cookie=ok"
        return httpx.Response(
            200,
            json=[
                {"symbol": "MAIN", "companyName": "Main Ltd", "series": "EQ"},
                {"symbol": "SMALL", "companyName": "Small Ltd", "series": "SME"},
                {
                    "symbol": "TYPEONLY",
                    "companyName": "Type Only Ltd",
                    "securityType": "SME",
                },
                {
                    "symbol": "BSEONLY",
                    "companyName": "BSE Only Ltd",
                    "series": "SME",
                    "isBse": "1",
                },
            ],
        )

    async def run() -> tuple[list[SourceIssue], list[SourceIssue]]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            main = await NSEScraper(client).fetch()
            emerge = await NSEEmergeScraper(client).fetch()
            return main, emerge

    main, emerge = asyncio.run(run())

    assert [issue.source_id for issue in main] == ["MAIN"]
    assert [issue.source_id for issue in emerge] == [
        "SMALL",
        "TYPEONLY",
        "BSEONLY",
    ]
    assert paths.count("/market-data/all-upcoming-issues-ipo") == 2
    assert paths[0] == "/market-data/all-upcoming-issues-ipo"


def test_bse_fetches_details_and_splits_boards() -> None:
    rows = [
        {
            "Scrip_cd": 101,
            "Scrip_Name": "Main Ltd",
            "IPO_NO": 9001,
            "IR_flag": "IPO",
            "eXCHANGE_PLATFORM": "MainBoard",
            "Status": "F",
        },
        {
            "Scrip_cd": 102,
            "Scrip_Name": "Small Ltd",
            "IPO_NO": 9002,
            "IR_flag": "IPO",
            "eXCHANGE_PLATFORM": "SME",
            "Status": "L",
        },
        {
            "Scrip_cd": 103,
            "Scrip_Name": "Rights Ltd",
            "IPO_NO": 9003,
            "IR_flag": "RI",
            "eXCHANGE_PLATFORM": "MainBoard",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("GetPublicIssue_par_updated/w"):
            return httpx.Response(200, json={"Table": rows})
        ipo_number = request.url.params["IPO_NO"]
        return httpx.Response(
            200,
            json={
                "IPONO_0": [
                    {
                        "Symbol": "MAIN" if ipo_number == "9001" else "SMALL",
                        "Market_Lot": "100",
                    }
                ]
            },
        )

    async def run() -> tuple[list[SourceIssue], list[SourceIssue]]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await BSEScraper(client).fetch(), await BSESMEScraper(client).fetch()

    main, sme = asyncio.run(run())

    assert len(main) == len(sme) == 1
    assert main[0].payload["Symbol"] == "MAIN"
    assert sme[0].payload["Symbol"] == "SMALL"
    assert main[0].board == "mainboard"
    assert sme[0].board == "SME"


def test_nse_emerge_keeps_isbse_row_and_enriches_missing_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/market-data/all-upcoming-issues-ipo":
            return httpx.Response(200, text="ok")
        if request.url.path == "/api/all-upcoming-issues":
            return httpx.Response(200, json=[])
        if request.url.path == "/api/ipo-current-issue":
            return httpx.Response(
                200,
                json=[
                    {
                        "companyName": "Optimystix Entertainment India Limited",
                        "symbol": "OPTIMYSTIX",
                        "series": "SME",
                        "isBse": "1",
                        "issueStartDate": "07-Aug-2026",
                        "issueEndDate": "11-Aug-2026",
                        "status": "Active",
                    }
                ],
            )
        assert request.url.path == "/api/ipo-detail"
        return httpx.Response(
            200,
            json={
                "issueInfo": {
                    "heading": "Optimystix Entertainment India Limited",
                    "dataList": [
                        {"title": "Price Range", "value": "Rs.166 to Rs.175"},
                        {
                            "title": "Issue Size",
                            "value": (
                                "Fresh issue up to 50,00,000 equity shares and "
                                "Offer for sale up to 12,00,000 equity shares"
                            ),
                        },
                        {"title": "Lot Size", "value": "800 Equity Shares"},
                        {
                            "title": "Name of the Registrar",
                            "value": "Maashitla Securities Private Limited",
                        },
                        {
                            "title": "Red Herring Prospectus",
                            "value": "https://nsearchives.nseindia.com/rhp.zip",
                        },
                    ],
                }
            },
        )

    async def run() -> list[SourceIssue]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await NSEEmergeScraper(client).fetch()

    issues = asyncio.run(run())
    result = IPONormalizer(today=date(2026, 8, 7)).merge(issues)

    assert len(issues) == 1
    assert issues[0].payload["issueSize"] == "6200000"
    assert not result.rejected
    ipo = result.ipos[0]
    assert ipo.symbol == "OPTIMYSTIX"
    assert ipo.board == "SME"
    assert ipo.price_band_high == Decimal("175")
    assert ipo.lot_size == 800
    assert ipo.issue_size == Decimal("108.50")
    assert ipo.registrar == "Maashitla Securities Private Limited"


def test_normalizer_produces_database_units_and_logs_every_missing_field(
    caplog,
) -> None:
    issue = SourceIssue(
        source="nse_mainboard",
        exchange="NSE",
        board="mainboard",
        source_id="EXAMPLE",
        payload={
            "companyName": "Example Limited",
            "symbol": "example",
            "issueStartDate": "07-Aug-2026",
            "issueEndDate": "11-Aug-2026",
            "issuePrice": "Rs. 100 to Rs. 125",
            "issueSize": "20000000",
            "series": "EQ",
            "status": "Active",
        },
    )

    with caplog.at_level(logging.WARNING):
        result = IPONormalizer(today=date(2026, 8, 7)).merge([issue])

    assert not result.rejected
    assert len(result.ipos) == 1
    ipo = result.ipos[0]
    assert ipo.symbol == "EXAMPLE"
    assert ipo.price_band_low == Decimal("100")
    assert ipo.price_band_high == Decimal("125")
    assert ipo.issue_size == Decimal("250.00")
    assert ipo.status == "open"
    messages = [record.message for record in caplog.records]
    assert any("field=lot_size" in message for message in messages)
    assert any("field=registrar" in message for message in messages)
    assert any("field=drhp_link" in message for message in messages)


def test_normalizer_merges_duplicates_and_retains_rejections(caplog) -> None:
    base = {
        "companyName": "Same Limited",
        "symbol": "SAME",
        "issueStartDate": "2026-08-10T00:00:00",
        "issueEndDate": "2026-08-12T00:00:00",
        "issuePrice": "10 - 12",
        "issueSize": "1000000",
        "status": "Forthcoming",
    }
    issues = [
        SourceIssue("source_a", "NSE", "mainboard", "1", base),
        SourceIssue(
            "source_b",
            "NSE",
            "mainboard",
            "2",
            {**base, "Registrar": "A Registrar^address"},
        ),
        SourceIssue("broken", "BSE", "SME", "3", {"Scrip_Name": "No Symbol"}),
    ]

    with caplog.at_level(logging.WARNING):
        result = IPONormalizer(today=date(2026, 8, 7)).merge(issues)

    assert len(result.ipos) == 1
    assert result.ipos[0].sources == ["source_a", "source_b"]
    assert result.ipos[0].registrar == "A Registrar"
    assert len(result.rejected) == 1
    assert result.rejected[0].source_id == "3"
    assert any("rejected issue" in record.message for record in caplog.records)
