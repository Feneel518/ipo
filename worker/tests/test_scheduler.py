import asyncio
from decimal import Decimal

import httpx
from tenacity import wait_none

from app.scheduler.repository import HealthAlert, WatchdogReport, WorkerRepository
from app.scheduler.service import ReliableJobRunner, WorkerScheduler
from app.subscriptions import NSESubscriptionScraper, SubscriptionObservation


class FakeHealthRepository:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def mark_started(self, name: str) -> int:
        self.events.append(("started", name))
        return 42

    def mark_succeeded(self, name: str, run_id: int | None = None) -> None:
        assert run_id == 42
        self.events.append(("succeeded", name))

    def mark_failed(self, name: str, error: str, run_id: int | None = None) -> None:
        assert run_id == 42
        self.events.append(("failed", name))


class FakeWatchdogRepository(FakeHealthRepository):
    def __init__(self, report: WatchdogReport) -> None:
        super().__init__()
        self.report = report
        self.notifications: dict[str, str] = {}

    def watchdog_report(
        self, expected_intervals: object, checked_at: object
    ) -> WatchdogReport:
        return self.report

    def notification_was_sent(self, key: str, fingerprint: str) -> bool:
        return self.notifications.get(key) == fingerprint

    def record_notification(
        self, key: str, fingerprint: str, sent_at: object
    ) -> None:
        self.notifications[key] = fingerprint

    def clear_resolved_alerts(self, active_keys: set[str]) -> None:
        self.notifications = {
            key: value
            for key, value in self.notifications.items()
            if not key.startswith("alert:") or key in active_keys
        }


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> bool:
        self.messages.append(message)
        return True


class FakeConnection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, object | None]] = []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: str, params: object | None = None) -> "FakeConnection":
        self.queries.append((query, params))
        return self


def test_clear_resolved_alerts_escapes_like_wildcard(monkeypatch) -> None:
    repository = WorkerRepository("postgresql://unused")
    connection = FakeConnection()
    monkeypatch.setattr(repository, "_connect", lambda: connection)

    repository.clear_resolved_alerts({"alert:calendar"})

    assert connection.queries
    assert "alert:%%" in connection.queries[0][0]


def test_scheduler_has_static_non_overlapping_jobs() -> None:
    worker = WorkerScheduler("postgresql://unused")
    jobs = {job.id: job for job in worker.scheduler.get_jobs()}

    assert set(jobs) == {"calendar", "eod", "subscription", "watchdog"}
    assert all(job.max_instances == 1 and job.coalesce for job in jobs.values())
    assert str(worker.scheduler.timezone) == "Asia/Kolkata"


def test_reliable_runner_retries_then_records_one_success() -> None:
    repository = FakeHealthRepository()
    runner = ReliableJobRunner(  # type: ignore[arg-type]
        repository, retry_wait=wait_none()
    )
    attempts = 0

    async def operation() -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("temporary")

    asyncio.run(runner.run("calendar", operation, timeout_seconds=30))

    assert attempts == 3
    assert repository.events == [("started", "calendar"), ("succeeded", "calendar")]


def test_reliable_runner_turns_timeout_into_health_failure() -> None:
    repository = FakeHealthRepository()
    runner = ReliableJobRunner(repository)  # type: ignore[arg-type]

    async def operation() -> None:
        await asyncio.sleep(1)

    asyncio.run(runner.run("subscription", operation, timeout_seconds=0.01))

    assert repository.events == [
        ("started", "subscription"),
        ("failed", "subscription"),
    ]


def test_watchdog_deduplicates_alerts_and_daily_digest() -> None:
    report = WatchdogReport(
        alerts=(
            HealthAlert(
                key="failure:calendar",
                fingerprint="network down",
                message="calendar: 3 consecutive failures",
            ),
        ),
        tracked_ipos=12,
    )
    repository = FakeWatchdogRepository(report)
    notifier = FakeNotifier()
    worker = WorkerScheduler(
        "postgresql://unused",
        notifier=notifier,  # type: ignore[arg-type]
        digest_hour=0,
    )
    worker.repository = repository  # type: ignore[assignment]
    worker.runner = ReliableJobRunner(repository)  # type: ignore[arg-type]

    asyncio.run(worker.run_watchdog())
    asyncio.run(worker.run_watchdog())

    assert len(notifier.messages) == 2
    assert notifier.messages[0].startswith("ALERT: IPO Dekho watchdog")
    assert "3 consecutive failures" in notifier.messages[0]
    assert notifier.messages[1].endswith(
        "1 health issue(s) active, 12 IPOs tracked"
    )


def test_watchdog_daily_digest_reports_all_green() -> None:
    repository = FakeWatchdogRepository(
        WatchdogReport(alerts=(), tracked_ipos=27)
    )
    notifier = FakeNotifier()
    worker = WorkerScheduler(
        "postgresql://unused",
        notifier=notifier,  # type: ignore[arg-type]
        digest_hour=0,
    )
    worker.repository = repository  # type: ignore[assignment]
    worker.runner = ReliableJobRunner(repository)  # type: ignore[arg-type]

    asyncio.run(worker.run_watchdog())

    assert notifier.messages == [
        "OK: IPO Dekho daily digest\nAll green, 27 IPOs tracked"
    ]


def test_nse_subscription_scraper_filters_and_parses_total() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/market-data/all-upcoming-issues-ipo":
            return httpx.Response(200, text="ok")
        return httpx.Response(
            200,
            json=[
                {"symbol": "OPENIPO", "noOfTime": "2.25"},
                {"symbol": "OTHER", "noOfTime": "4.0"},
                {"symbol": "BROKEN", "noOfTime": "-"},
            ],
        )

    async def run() -> list[SubscriptionObservation]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await NSESubscriptionScraper(client).fetch({"openipo", "broken"})

    assert asyncio.run(run()) == [
        SubscriptionObservation("OPENIPO", "total", Decimal("2.25"))
    ]
