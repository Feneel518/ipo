import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt
from tenacity.wait import wait_exponential_jitter

from app.config import Settings
from app.prices.repository import PriceRepository
from app.prices.service import PriceIngestionService
from app.scheduler.repository import WorkerRepository
from app.scrapers import fetch_ipo_issues
from app.scrapers.normalizer import IPONormalizer
from app.subscriptions import NSESubscriptionScraper

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class TelegramNotifier:
    def __init__(self, token: str | None, chat_id: str | None) -> None:
        self._token = token
        self._chat_id = chat_id

    @property
    def configured(self) -> bool:
        return bool(self._token and self._chat_id)

    async def send(self, message: str) -> bool:
        if not self.configured:
            logger.warning("watchdog alert not sent: Telegram is not configured")
            return False
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={"chat_id": self._chat_id, "text": message},
            )
            response.raise_for_status()
        return True


class ReliableJobRunner:
    def __init__(self, repository: WorkerRepository, *, retry_wait: Any = None) -> None:
        self._repository = repository
        self._retry_wait = retry_wait or wait_exponential_jitter(
            initial=5, max=60, jitter=3
        )

    async def run(
        self,
        name: str,
        operation: Callable[[], Awaitable[None]],
        *,
        timeout_seconds: float,
    ) -> None:
        run_id = await asyncio.to_thread(self._repository.mark_started, name)

        async def attempt() -> None:
            async for attempt_state in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=self._retry_wait,
                retry=retry_if_exception_type(Exception),
                reraise=True,
            ):
                with attempt_state:
                    await operation()

        try:
            async with asyncio.timeout(timeout_seconds):
                await attempt()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("scheduled job failed name=%s", name)
            try:
                error = f"{type(exc).__name__}: {exc}"
                if run_id is None:
                    await asyncio.to_thread(self._repository.mark_failed, name, error)
                else:
                    await asyncio.to_thread(
                        self._repository.mark_failed, name, error, run_id
                    )
            except Exception:
                logger.exception("could not record failed job health name=%s", name)
            return
        if run_id is None:
            await asyncio.to_thread(self._repository.mark_succeeded, name)
        else:
            await asyncio.to_thread(self._repository.mark_succeeded, name, run_id)


class WorkerScheduler:
    EXPECTED_INTERVALS = {
        "calendar": timedelta(hours=1),
        "eod": timedelta(days=1),
        "subscription": timedelta(minutes=4),
    }

    def __init__(
        self,
        database_url: str,
        *,
        notifier: TelegramNotifier | None = None,
        scheduler: AsyncIOScheduler | None = None,
        digest_hour: int = 9,
    ) -> None:
        self.repository = WorkerRepository(database_url)
        self.price_service = PriceIngestionService(PriceRepository(database_url))
        self.subscription_scraper = NSESubscriptionScraper()
        self.notifier = notifier or TelegramNotifier(None, None)
        self.runner = ReliableJobRunner(self.repository)
        self.scheduler = scheduler or AsyncIOScheduler(timezone=IST)
        self.digest_hour = digest_hour
        self._register_jobs()

    def _register_jobs(self) -> None:
        common = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 60}
        self.scheduler.add_job(
            self.run_calendar,
            "interval",
            hours=1,
            id="calendar",
            replace_existing=True,
            **common,
        )
        self.scheduler.add_job(
            self.run_eod,
            "cron",
            hour=18,
            minute=45,
            id="eod",
            replace_existing=True,
            **common,
        )
        self.scheduler.add_job(
            self.run_subscriptions,
            "interval",
            minutes=4,
            id="subscription",
            replace_existing=True,
            **common,
        )
        self.scheduler.add_job(
            self.run_watchdog,
            "interval",
            minutes=15,
            id="watchdog",
            replace_existing=True,
            **common,
        )

    async def run_calendar(self) -> None:
        async def operation() -> None:
            issues = await fetch_ipo_issues()
            result = IPONormalizer(today=datetime.now(IST).date()).merge(issues)
            count = await asyncio.to_thread(
                self.repository.save_calendar,
                result,
                issues,
                datetime.now(IST),
            )
            logger.info(
                "calendar ingestion complete upserted=%d rejected=%d",
                count,
                len(result.rejected),
            )

        await self.runner.run("calendar", operation, timeout_seconds=180)

    async def run_eod(self) -> None:
        async def operation() -> None:
            result = await self.price_service.daily(datetime.now(IST).date())
            logger.info("EOD ingestion complete result=%s", result)

        await self.runner.run("eod", operation, timeout_seconds=900)

    async def run_subscriptions(self) -> None:
        async def operation() -> None:
            open_ipos = await asyncio.to_thread(self.repository.list_open_ipos)
            if not open_ipos:
                logger.info("subscription poll skipped: no open IPOs")
                return
            nse_symbols = {ipo.symbol for ipo in open_ipos if ipo.exchange == "NSE"}
            observations = await self.subscription_scraper.fetch(nse_symbols)
            ids = {(ipo.exchange, ipo.symbol): ipo.ipo_id for ipo in open_ipos}
            count = await asyncio.to_thread(
                self.repository.save_subscriptions,
                ids,
                observations,
                datetime.now(IST),
            )
            unsupported = sum(ipo.exchange != "NSE" for ipo in open_ipos)
            logger.info(
                "subscription poll complete inserted=%d bse_unavailable=%d",
                count,
                unsupported,
            )

        await self.runner.run("subscription", operation, timeout_seconds=150)

    async def run_watchdog(self) -> None:
        async def operation() -> None:
            checked_at = datetime.now(IST)
            report = await asyncio.to_thread(
                self.repository.watchdog_report,
                self.EXPECTED_INTERVALS,
                checked_at,
            )
            active_keys = {f"alert:{alert.key}" for alert in report.alerts}
            for alert in report.alerts:
                notification_key = f"alert:{alert.key}"
                already_sent = await asyncio.to_thread(
                    self.repository.notification_was_sent,
                    notification_key,
                    alert.fingerprint,
                )
                if already_sent:
                    continue
                sent = await self.notifier.send(
                    "ALERT: IPO Dekho watchdog\n" + alert.message
                )
                if sent is not False:
                    await asyncio.to_thread(
                        self.repository.record_notification,
                        notification_key,
                        alert.fingerprint,
                        checked_at,
                    )

            await asyncio.to_thread(self.repository.clear_resolved_alerts, active_keys)

            if checked_at.hour >= self.digest_hour:
                digest_key = "digest"
                digest_fingerprint = checked_at.date().isoformat()
                digest_sent = await asyncio.to_thread(
                    self.repository.notification_was_sent,
                    digest_key,
                    digest_fingerprint,
                )
                if not digest_sent:
                    if report.alerts:
                        status_line = f"{len(report.alerts)} health issue(s) active"
                        prefix = "ATTENTION:"
                    else:
                        status_line = "All green"
                        prefix = "OK:"
                    sent = await self.notifier.send(
                        f"{prefix} IPO Dekho daily digest\n"
                        f"{status_line}, {report.tracked_ipos} IPOs tracked"
                    )
                    if sent is not False:
                        await asyncio.to_thread(
                            self.repository.record_notification,
                            digest_key,
                            digest_fingerprint,
                            checked_at,
                        )

        await self.runner.run("watchdog", operation, timeout_seconds=120)

    def start(self) -> None:
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)


def create_worker_scheduler(settings: Settings) -> WorkerScheduler | None:
    if not settings.scheduler_enabled or settings.database_url is None:
        return None
    token = (
        settings.telegram_bot_token.get_secret_value()
        if settings.telegram_bot_token
        else None
    )
    notifier = TelegramNotifier(token, settings.telegram_chat_id)
    return WorkerScheduler(
        settings.database_url.get_secret_value(),
        notifier=notifier,
        digest_hour=settings.watchdog_digest_hour,
    )
