from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

Exchange = Literal["NSE", "BSE"]


@dataclass(frozen=True, slots=True)
class EODPrice:
    symbol: str | None
    security_code: str | None
    open: Decimal
    close: Decimal


@dataclass(frozen=True, slots=True)
class Bhavcopy:
    exchange: Exchange
    trade_date: date
    by_symbol: dict[str, EODPrice]
    by_security_code: dict[str, EODPrice]

    def find(self, symbol: str, security_code: str | None) -> EODPrice | None:
        if security_code:
            match = self.by_security_code.get(security_code.strip().upper())
            if match:
                return match
        return self.by_symbol.get(symbol.strip().upper())


@dataclass(frozen=True, slots=True)
class IPOSecurity:
    ipo_id: int
    symbol: str
    exchange: Exchange
    exchange_security_code: str | None
    listing_date: date


@dataclass(frozen=True, slots=True)
class IngestionResult:
    files_loaded: int
    files_unavailable: int
    listing_prices_updated: int
    current_prices_updated: int
    unmatched_ipos: int
    current_price_date: date | None
