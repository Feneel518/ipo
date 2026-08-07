import csv
import io
import re
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from app.prices.models import Bhavcopy, EODPrice, Exchange
from app.scrapers.http import BROWSER_HEADERS, exchange_client

UDIFF_START = date(2024, 7, 8)
NSE_ARCHIVE = "https://nsearchives.nseindia.com"
BSE_ARCHIVE = "https://www.bseindia.com"


class BhavcopyUnavailable(Exception):
    """The exchange did not publish a bhavcopy for a date (holiday/weekend)."""


def _clean_symbol(value: str | None) -> str | None:
    symbol = re.sub(r"\s+", "", value or "").upper().rstrip("#")
    return symbol or None


def _decimal(value: str | None) -> Decimal | None:
    try:
        parsed = Decimal((value or "").strip())
    except InvalidOperation:
        return None
    return parsed if parsed >= 0 else None


def parse_bhavcopy(payload: bytes, exchange: Exchange, expected_date: date) -> Bhavcopy:
    """Parse legacy or UDiFF NSE/BSE CSV bytes into one common shape."""

    text = payload.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("bhavcopy has no CSV header")

    fields = {field.strip() for field in reader.fieldnames}
    udiff = "TckrSymb" in fields
    legacy_nse = "SYMBOL" in fields
    legacy_bse = "SC_CODE" in fields
    if not (udiff or legacy_nse or legacy_bse):
        raise ValueError(f"unrecognized bhavcopy columns: {sorted(fields)!r}")

    by_symbol: dict[str, EODPrice] = {}
    by_code: dict[str, EODPrice] = {}
    for row in reader:
        if udiff and str(row.get("FinInstrmTp") or "").strip().upper() != "STK":
            continue
        symbol = _clean_symbol(row.get("TckrSymb") or row.get("SYMBOL"))
        code = str(row.get("FinInstrmId") or row.get("SC_CODE") or "").strip()
        code = code.upper() or None
        open_price = _decimal(row.get("OpnPric") or row.get("OPEN"))
        close_price = _decimal(row.get("ClsPric") or row.get("CLOSE"))
        if open_price is None or close_price is None:
            continue
        price = EODPrice(symbol, code, open_price, close_price)
        if symbol:
            by_symbol[symbol] = price
        if code:
            by_code[code] = price

    if not by_symbol and not by_code:
        raise ValueError("bhavcopy contained no equity price rows")
    return Bhavcopy(exchange, expected_date, by_symbol, by_code)


class BhavcopyClient:
    """Download official NSE and BSE cash-market EOD files."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @staticmethod
    def url_for(exchange: Exchange, trade_date: date) -> str:
        ymd = trade_date.strftime("%Y%m%d")
        if exchange == "NSE":
            if trade_date >= UDIFF_START:
                return (
                    f"{NSE_ARCHIVE}/content/cm/"
                    f"BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
                )
            month = trade_date.strftime("%b").upper()
            filename = f"cm{trade_date:%d}{month}{trade_date:%Y}bhav.csv.zip"
            return (
                f"{NSE_ARCHIVE}/content/historical/EQUITIES/"
                f"{trade_date:%Y}/{month}/{filename}"
            )
        if trade_date >= UDIFF_START:
            return (
                f"{BSE_ARCHIVE}/download/BhavCopy/Equity/"
                f"BhavCopy_BSE_CM_0_0_0_{ymd}_F_0000.csv"
            )
        return f"{BSE_ARCHIVE}/download/BhavCopy/Equity/EQ{trade_date:%d%m%y}_CSV.ZIP"

    async def fetch(self, exchange: Exchange, trade_date: date) -> Bhavcopy:
        headers = {
            **BROWSER_HEADERS,
            "Accept": "text/csv, application/zip, application/octet-stream, */*",
            "Referer": (
                "https://www.nseindia.com/all-reports"
                if exchange == "NSE"
                else "https://www.bseindia.com/markets/MarketInfo/BhavCopy.aspx"
            ),
        }
        url = self.url_for(exchange, trade_date)
        async with exchange_client(self._client, headers=headers) as client:
            response = await client.get(url, headers=headers)
        if response.status_code in {403, 404}:
            raise BhavcopyUnavailable(f"{exchange} has no file for {trade_date}")
        response.raise_for_status()

        content = response.content
        if content.startswith(b"PK"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    csv_names = [
                        name
                        for name in archive.namelist()
                        if name.lower().endswith(".csv")
                    ]
                    if not csv_names:
                        raise ValueError("bhavcopy zip contains no CSV")
                    content = archive.read(csv_names[0])
            except zipfile.BadZipFile as exc:
                raise ValueError(f"invalid bhavcopy zip from {url}") from exc
        elif b"<html" in content[:500].lower():
            raise BhavcopyUnavailable(f"{exchange} has no file for {trade_date}")
        return parse_bhavcopy(content, exchange, trade_date)
