from collections.abc import Iterable
from datetime import date

import psycopg
from psycopg.rows import class_row

from app.prices.models import EODPrice, IPOSecurity
from app.scrapers.models import NormalizedIPO


class PriceRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        connection = psycopg.connect(self._database_url, connect_timeout=20)
        connection.execute("SET statement_timeout = '30s'")
        return connection

    def listed_ipos(self, start: date, end: date) -> list[IPOSecurity]:
        query = """
            SELECT id AS ipo_id, symbol, exchange, exchange_security_code,
                   listing_date
            FROM ipos
            WHERE listing_date BETWEEN %s AND %s
              AND exchange IN ('NSE', 'BSE')
            ORDER BY listing_date, id
        """
        with self._connect() as connection:
            with connection.cursor(row_factory=class_row(IPOSecurity)) as cursor:
                return list(cursor.execute(query, (start, end)).fetchall())

    def listed_ipos_missing_prices(self, start: date, end: date) -> list[IPOSecurity]:
        query = """
            SELECT i.id AS ipo_id, i.symbol, i.exchange,
                   i.exchange_security_code, i.listing_date
            FROM ipos i
            LEFT JOIN listing_performance lp ON lp.ipo_id = i.id
            WHERE i.listing_date BETWEEN %s AND %s
              AND i.exchange IN ('NSE', 'BSE')
              AND (
                  lp.listing_open_price IS NULL
                  OR lp.listing_close_price IS NULL
              )
            ORDER BY i.listing_date, i.id
        """
        with psycopg.connect(self._database_url) as connection:
            with connection.cursor(row_factory=class_row(IPOSecurity)) as cursor:
                return list(cursor.execute(query, (start, end)).fetchall())

    def upsert_ipos(self, ipos: Iterable[NormalizedIPO]) -> int:
        columns = (
            "name",
            "symbol",
            "exchange",
            "exchange_security_code",
            "board",
            "price_band_low",
            "price_band_high",
            "lot_size",
            "issue_size",
            "open_date",
            "close_date",
            "allotment_date",
            "refund_date",
            "listing_date",
            "registrar",
            "status",
            "drhp_link",
        )
        rows = [
            tuple(ipo.as_upsert_values()[column] for column in columns) for ipo in ipos
        ]
        if not rows:
            return 0
        query = """
            INSERT INTO ipos (
                name, symbol, exchange, exchange_security_code, board,
                price_band_low, price_band_high, lot_size, issue_size,
                open_date, close_date, allotment_date, refund_date, listing_date,
                registrar, status, drhp_link
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (symbol, exchange) DO UPDATE SET
                name = EXCLUDED.name,
                exchange_security_code = COALESCE(
                    EXCLUDED.exchange_security_code, ipos.exchange_security_code
                ),
                board = EXCLUDED.board,
                price_band_low = COALESCE(
                    EXCLUDED.price_band_low, ipos.price_band_low
                ),
                price_band_high = COALESCE(
                    EXCLUDED.price_band_high, ipos.price_band_high
                ),
                lot_size = COALESCE(EXCLUDED.lot_size, ipos.lot_size),
                issue_size = COALESCE(EXCLUDED.issue_size, ipos.issue_size),
                open_date = COALESCE(EXCLUDED.open_date, ipos.open_date),
                close_date = COALESCE(EXCLUDED.close_date, ipos.close_date),
                allotment_date = COALESCE(
                    EXCLUDED.allotment_date, ipos.allotment_date
                ),
                refund_date = COALESCE(EXCLUDED.refund_date, ipos.refund_date),
                listing_date = COALESCE(EXCLUDED.listing_date, ipos.listing_date),
                registrar = COALESCE(EXCLUDED.registrar, ipos.registrar),
                status = EXCLUDED.status,
                drhp_link = COALESCE(EXCLUDED.drhp_link, ipos.drhp_link)
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(query, rows)
                changed = cursor.rowcount
        return changed

    def all_listed_ipos(self, as_of: date) -> list[IPOSecurity]:
        return self.listed_ipos(date.min, as_of)

    def update_listing_prices(
        self, values: Iterable[tuple[IPOSecurity, EODPrice, date]]
    ) -> int:
        rows = [
            (ipo.ipo_id, price.open, price.close, day) for ipo, price, day in values
        ]
        if not rows:
            return 0
        query = """
            INSERT INTO listing_performance (
                ipo_id, listing_open_price, listing_close_price, listing_price_date
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (ipo_id) DO UPDATE SET
                listing_open_price = EXCLUDED.listing_open_price,
                listing_close_price = EXCLUDED.listing_close_price,
                listing_price_date = EXCLUDED.listing_price_date
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(query, rows)
                changed = cursor.rowcount
        return changed

    def update_current_prices(
        self, values: Iterable[tuple[IPOSecurity, EODPrice, date]]
    ) -> int:
        rows = [(ipo.ipo_id, price.close, day) for ipo, price, day in values]
        if not rows:
            return 0
        query = """
            INSERT INTO listing_performance (ipo_id, current_price, current_price_date)
            VALUES (%s, %s, %s)
            ON CONFLICT (ipo_id) DO UPDATE SET
                current_price = EXCLUDED.current_price,
                current_price_date = EXCLUDED.current_price_date
            WHERE listing_performance.current_price_date IS NULL
               OR listing_performance.current_price_date <= EXCLUDED.current_price_date
        """
        with psycopg.connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(query, rows)
                changed = cursor.rowcount
        return changed
