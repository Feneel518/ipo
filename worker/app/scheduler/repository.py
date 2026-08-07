from dataclasses import dataclass
from datetime import datetime, timedelta

import psycopg
from psycopg.types.json import Jsonb

from app.scrapers.models import NormalizationResult, SourceIssue
from app.subscriptions import SubscriptionObservation


@dataclass(frozen=True, slots=True)
class OpenIPO:
    ipo_id: int
    symbol: str
    exchange: str


@dataclass(frozen=True, slots=True)
class HealthFailure:
    name: str
    last_error: str
    consecutive_failures: int


@dataclass(frozen=True, slots=True)
class HealthAlert:
    key: str
    fingerprint: str
    message: str


@dataclass(frozen=True, slots=True)
class WatchdogReport:
    alerts: tuple[HealthAlert, ...]
    tracked_ipos: int


class WorkerRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        connection = psycopg.connect(self._database_url, connect_timeout=20)
        connection.execute("SET statement_timeout = '30s'")
        return connection

    def save_calendar(
        self,
        result: NormalizationResult,
        raw_issues: list[SourceIssue],
        captured_at: datetime,
    ) -> int:
        query = """
            INSERT INTO ipos (
                name, symbol, exchange, exchange_security_code, board,
                price_band_low, price_band_high, lot_size, issue_size,
                open_date, close_date, allotment_date, refund_date,
                listing_date, registrar, status, drhp_link
            ) VALUES (
                %(name)s, %(symbol)s, %(exchange)s,
                %(exchange_security_code)s, %(board)s, %(price_band_low)s,
                %(price_band_high)s, %(lot_size)s, %(issue_size)s,
                %(open_date)s, %(close_date)s, %(allotment_date)s,
                %(refund_date)s, %(listing_date)s, %(registrar)s,
                %(status)s, %(drhp_link)s
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
        raw_query = """
            INSERT INTO raw_snapshots (scraper_name, captured_at, raw_payload)
            VALUES (%s, %s, %s)
        """
        status_query = """
            UPDATE ipos
            SET status = CASE
                WHEN open_date <= %s AND close_date >= %s THEN 'open'
                WHEN close_date < %s THEN 'closed'
                WHEN open_date > %s THEN 'upcoming'
                ELSE status
            END
            WHERE status IN ('upcoming', 'open', 'closed')
        """
        today = captured_at.date()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                if result.ipos:
                    cursor.executemany(
                        query, [ipo.as_upsert_values() for ipo in result.ipos]
                    )
                if raw_issues:
                    cursor.executemany(
                        raw_query,
                        [
                            (issue.source, captured_at, Jsonb(issue.payload))
                            for issue in raw_issues
                        ],
                    )
                # Rows can disappear from an exchange's current feed after close.
                # Reconcile all date-driven states so such IPOs cannot stay open.
                cursor.execute(status_query, (today, today, today, today))
        return len(result.ipos)

    def list_open_ipos(self) -> list[OpenIPO]:
        query = """
            SELECT id, symbol, exchange
            FROM ipos
            WHERE status = 'open'
            ORDER BY id
        """
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [OpenIPO(int(row[0]), str(row[1]), str(row[2])) for row in rows]

    def save_subscriptions(
        self,
        ipo_ids: dict[tuple[str, str], int],
        observations: list[SubscriptionObservation],
        captured_at: datetime,
    ) -> int:
        rows = [
            (ipo_ids[("NSE", item.symbol)], captured_at, item.category, item.multiple)
            for item in observations
            if ("NSE", item.symbol) in ipo_ids
        ]
        if not rows:
            return 0
        query = """
            INSERT INTO subscription_snapshots (
                ipo_id, captured_at, category, subscription_multiple
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (ipo_id, captured_at, category) DO NOTHING
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(query, rows)
                return cursor.rowcount

    def mark_started(self, name: str) -> int:
        health_query = """
            INSERT INTO scraper_health (name, last_run)
            VALUES (%s, now())
            ON CONFLICT (name) DO UPDATE SET last_run = EXCLUDED.last_run
        """
        history_query = """
            INSERT INTO job_run_history (name)
            VALUES (%s)
            RETURNING id
        """
        with self._connect() as connection:
            connection.execute(health_query, (name,))
            row = connection.execute(history_query, (name,)).fetchone()
        assert row is not None
        return int(row[0])

    def mark_succeeded(self, name: str, run_id: int | None = None) -> None:
        query = """
            INSERT INTO scraper_health (
                name, last_run, last_success, last_error, consecutive_failures
            ) VALUES (%s, now(), now(), NULL, 0)
            ON CONFLICT (name) DO UPDATE SET
                last_success = EXCLUDED.last_success,
                last_error = NULL,
                consecutive_failures = 0
        """
        with self._connect() as connection:
            connection.execute(query, (name,))
            if run_id is not None:
                connection.execute(
                    """
                    UPDATE job_run_history
                    SET status = 'succeeded', finished_at = now(), error = NULL
                    WHERE id = %s AND status = 'running'
                    """,
                    (run_id,),
                )

    def mark_failed(self, name: str, error: str, run_id: int | None = None) -> None:
        query = """
            INSERT INTO scraper_health (
                name, last_run, last_error, consecutive_failures
            ) VALUES (%s, now(), %s, 1)
            ON CONFLICT (name) DO UPDATE SET
                last_error = EXCLUDED.last_error,
                consecutive_failures = scraper_health.consecutive_failures + 1
        """
        with self._connect() as connection:
            connection.execute(query, (name, error[:4000]))
            if run_id is not None:
                connection.execute(
                    """
                    UPDATE job_run_history
                    SET status = 'failed', finished_at = now(), error = %s
                    WHERE id = %s AND status = 'running'
                    """,
                    (error[:4000], run_id),
                )

    def failures(self) -> list[HealthFailure]:
        query = """
            SELECT name, last_error, consecutive_failures
            FROM scraper_health
            WHERE consecutive_failures > 0 AND last_error IS NOT NULL
            ORDER BY name
        """
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [HealthFailure(str(row[0]), str(row[1]), int(row[2])) for row in rows]

    def watchdog_report(
        self,
        expected_intervals: dict[str, timedelta],
        checked_at: datetime,
    ) -> WatchdogReport:
        health_query = """
            SELECT name, last_success, last_error, consecutive_failures
            FROM scraper_health
            WHERE name = ANY(%s)
        """
        stale_subscription_query = """
            SELECT i.id, i.name, i.symbol, i.exchange, max(s.captured_at)
            FROM ipos AS i
            LEFT JOIN subscription_snapshots AS s ON s.ipo_id = i.id
            WHERE i.status = 'open'
            GROUP BY i.id, i.name, i.symbol, i.exchange
            HAVING max(s.captured_at) IS NULL OR max(s.captured_at) < %s
            ORDER BY i.id
        """
        with self._connect() as connection:
            health_rows = connection.execute(
                health_query, (list(expected_intervals),)
            ).fetchall()
            stale_rows = connection.execute(
                stale_subscription_query, (checked_at - timedelta(minutes=30),)
            ).fetchall()
            tracked_ipos = int(
                connection.execute("SELECT count(*) FROM ipos").fetchone()[0]
            )

        by_name = {str(row[0]): row for row in health_rows}
        alerts: list[HealthAlert] = []
        for name, interval in expected_intervals.items():
            row = by_name.get(name)
            last_success = row[1] if row else None
            last_error = str(row[2]) if row and row[2] is not None else None
            consecutive_failures = int(row[3]) if row else 0

            if consecutive_failures >= 3:
                error = last_error or "unknown error"
                alerts.append(
                    HealthAlert(
                        key=f"failure:{name}",
                        # Alert once per incident; a changed error is a useful
                        # update, while a rising counter would only be noise.
                        fingerprint=error,
                        message=(
                            f"{name}: {consecutive_failures} consecutive failures"
                            f"\nLast error: {error}"
                        ),
                    )
                )

            stale_after = checked_at - (interval * 2)
            if last_success is None or last_success < stale_after:
                success_text = (
                    last_success.isoformat() if last_success is not None else "never"
                )
                alerts.append(
                    HealthAlert(
                        key=f"stale:{name}",
                        fingerprint=success_text,
                        message=(
                            f"{name}: no successful run within {interval * 2}"
                            f"\nLast success: {success_text}"
                        ),
                    )
                )

        for ipo_id, name, symbol, exchange, last_snapshot in stale_rows:
            snapshot_text = (
                last_snapshot.isoformat() if last_snapshot is not None else "never"
            )
            alerts.append(
                HealthAlert(
                    key=f"subscription:{ipo_id}",
                    fingerprint=snapshot_text,
                    message=(
                        f"{name} ({exchange}:{symbol}): no subscription snapshot "
                        f"in 30 minutes\nLast snapshot: {snapshot_text}"
                    ),
                )
            )

        return WatchdogReport(tuple(alerts), tracked_ipos)

    def notification_was_sent(self, key: str, fingerprint: str) -> bool:
        query = """
            SELECT EXISTS (
                SELECT 1 FROM watchdog_notifications
                WHERE notification_key = %s AND fingerprint = %s
            )
        """
        with self._connect() as connection:
            return bool(connection.execute(query, (key, fingerprint)).fetchone()[0])

    def record_notification(
        self, key: str, fingerprint: str, sent_at: datetime
    ) -> None:
        query = """
            INSERT INTO watchdog_notifications (
                notification_key, fingerprint, sent_at
            ) VALUES (%s, %s, %s)
            ON CONFLICT (notification_key) DO UPDATE SET
                fingerprint = EXCLUDED.fingerprint,
                sent_at = EXCLUDED.sent_at
        """
        with self._connect() as connection:
            connection.execute(query, (key, fingerprint, sent_at))

    def clear_resolved_alerts(self, active_keys: set[str]) -> None:
        with self._connect() as connection:
            if active_keys:
                connection.execute(
                    """
                    DELETE FROM watchdog_notifications
                    WHERE notification_key LIKE 'alert:%%'
                      AND NOT (notification_key = ANY(%s))
                    """,
                    (list(active_keys),),
                )
            else:
                connection.execute(
                    """
                    DELETE FROM watchdog_notifications
                    WHERE notification_key LIKE 'alert:%%'
                    """
                )
