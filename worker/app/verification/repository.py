from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row


class VerificationRepository:
    """Read-only queries used by the burn-in verification command."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        connection = psycopg.connect(self._database_url, connect_timeout=20)
        connection.execute("SET statement_timeout = '30s'")
        return connection

    def current_ipos(self) -> list[dict[str, Any]]:
        query = """
            SELECT name, symbol, exchange, board, status, open_date, close_date,
                   listing_date, updated_at
            FROM ipos
            WHERE status IN ('upcoming', 'open')
            ORDER BY exchange, board, symbol
        """
        with self._connect() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return list(cursor.execute(query).fetchall())

    def table_freshness(self) -> list[dict[str, Any]]:
        query = """
            SELECT 'ipos' AS table_name, count(*) AS row_count,
                   max(updated_at) AS freshest_at FROM ipos
            UNION ALL
            SELECT 'subscription_snapshots', count(*), max(captured_at)
              FROM subscription_snapshots
            UNION ALL
            SELECT 'listing_performance', count(*), max(updated_at)
              FROM listing_performance
            UNION ALL
            SELECT 'scraper_health', count(*), max(last_run)
              FROM scraper_health
            UNION ALL
            SELECT 'raw_snapshots', count(*), max(captured_at)
              FROM raw_snapshots
            UNION ALL
            SELECT 'job_run_history', count(*), max(started_at)
              FROM job_run_history
            UNION ALL
            SELECT 'watchdog_notifications', count(*), max(sent_at)
              FROM watchdog_notifications
            ORDER BY table_name
        """
        with self._connect() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return list(cursor.execute(query).fetchall())

    def health_since(self, since: datetime) -> list[dict[str, Any]]:
        query = """
            SELECT id, name, started_at, finished_at, status, error
            FROM job_run_history
            WHERE started_at >= %s
            ORDER BY started_at DESC, id DESC
        """
        with self._connect() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return list(cursor.execute(query, (since,)).fetchall())

    def current_health(self) -> list[dict[str, Any]]:
        query = """
            SELECT name, last_run, last_success, last_error,
                   consecutive_failures
            FROM scraper_health
            ORDER BY name
        """
        with self._connect() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return list(cursor.execute(query).fetchall())
