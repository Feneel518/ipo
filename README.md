# IPO Dekho

Monorepo for the IPO Dekho web application and background worker.

## Layout

- `web/` — Next.js (App Router) + Tailwind + shadcn/ui web application
- `worker/` — Python worker with a FastAPI HTTP surface
- `database/` — versioned PostgreSQL migrations and scraper write contract

The two legacy source directories currently at the workspace root are preserved
unchanged and ignored by Git pending a deliberate migration into the worker.

## Run the web app locally

```powershell
cd web
npm install
Copy-Item .env.example .env
# Fill DATABASE_URL with the web_readonly connection string — see
# database/README.md#web-app-read-access. Never use the worker's read-write
# DATABASE_URL here.
npm run dev
```

The web app reads the same Postgres database the worker writes, but only
through the `web_readonly` role (`database/migrations/0005_web_readonly_role.sql`),
which has `SELECT` on `ipos`, `subscription_snapshots`, and
`listing_performance` and nothing else — a bug in the web app cannot corrupt
data the worker owns. All database reads go through `web/src/lib/ipo.ts`
(`getLiveIpos`, `getIpoBySlug`, `getSubscriptionHistory`) so caching policy
lives in one place.

## Run the worker locally

```powershell
cd worker
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item ..\.env.example .env
uvicorn app.main:app --reload
```

The service exposes `GET /health/live` and `GET /health/ready`. API docs are at
`/docs` outside production.

With `DATABASE_URL` configured, the same process runs four guarded APScheduler
jobs in `Asia/Kolkata`: calendar ingestion hourly, subscription snapshots every
4 minutes (a DB no-op when no IPO is open), EOD prices at 18:45, and a watchdog
every 15 minutes. Every job records success or failure in `scraper_health`, has
three exponential-backoff attempts, a hard deadline, `max_instances=1`, and
coalescing. Set `SCHEDULER_ENABLED=false` when running an API-only replica.

The watchdog alerts a personal Telegram chat after three consecutive failures,
when a scraper has not succeeded within twice its expected interval, or when an
open IPO has no subscription snapshot for 30 minutes. Notifications are
deduplicated durably, and a once-daily digest reports either `All green` or the
number of active issues plus the total IPOs tracked. Configure
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and optionally
`WATCHDOG_DIGEST_HOUR` (default `9`, Asia/Kolkata).

The subscription adapter currently records the official NSE total multiple.
BSE-only and category-level subscription sources remain intentionally
unsupported until an official, stable feed is integrated.

## Official exchange ingestion

`worker/app/scrapers` contains HTTP-first adapters for NSE mainboard, NSE
Emerge, BSE mainboard, and BSE SME. NSE requests warm a cookie-bearing session
before calling its JSON endpoints. BSE reads its official issue list and then
enriches each row from the official issue-detail endpoint. No browser runtime
is required.

Run and normalize all four sources with:

```python
from app.scrapers import scrape_ipos

result = await scrape_ipos()
for ipo in result.ipos:
    values = ipo.as_upsert_values()
```

`result.rejected` retains records missing a required name or symbol. Missing,
invalid, and conflicting normalized fields are logged with their source and
source identifier; source payloads remain available for raw snapshot storage.

Set `DATABASE_URL` to the pooled Postgres connection string supplied by Neon or
Supabase. Secrets belong in local environment files or the deployment platform's
secret manager, never in version control.

## Listing and current prices

Apply all database migrations in numeric order, then run the one-off three-year
backfill:

```powershell
cd worker
ipo-prices backfill --start 2023-08-07
```

The command first seeds the catalog from NSE's official past-issues feed. It then
downloads only the distinct IPO listing dates from official NSE/BSE EOD bhavcopy
archives, records listing-day open and close, and sets current prices from the
newest available trading file. It is safe to rerun.

Run the ongoing job once each trading day after both exchanges publish EOD data
(for example, 19:00 Asia/Kolkata):

```powershell
ipo-prices daily
```

The daily command looks back across weekends and exchange holidays, refuses to
replace a newer current price with an older one, and fills listing prices for
IPOs that debuted that day. Its JSON output is suitable for scheduler logs and
alerting; a non-zero exit indicates a download, parse, or database failure.

## Daily burn-in verification

Dump a fresh official-exchange comparison, freshness for every worker table,
and the last 24 hours of scheduled-job health:

```powershell
cd worker
ipo-verify
```

The JSON includes the complete current database and exchange lists plus
`missing_from_database` and `missing_from_exchange` differences. Empty tables
report `freshest_at: null` instead of appearing fresh. Use `ipo-verify --strict`
in automation to exit non-zero when the lists differ, an exchange row is
rejected, a terminal job failure occurred, or a run has been stuck for more
than 20 minutes. The command is read-only; the exchange side is fetched live
from the same official NSE and BSE adapters used by ingestion.
