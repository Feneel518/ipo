# Database contract

The SQL files in `migrations/` are ordered PostgreSQL migrations. Apply all of
them in numeric order to a new database before starting the worker.

## Scraper write rules

IPO detail scrapers must normalize `symbol` and `exchange` to uppercase and
upsert on their natural key. They must never blindly insert an IPO:

```sql
INSERT INTO ipos (
    name, symbol, exchange, exchange_security_code, board, price_band_low, price_band_high,
    lot_size, issue_size, open_date, close_date, allotment_date,
    refund_date, listing_date, registrar, status, drhp_link
)
VALUES (
    :name, upper(btrim(:symbol)), upper(btrim(:exchange)),
    upper(btrim(:exchange_security_code)), :board,
    :price_band_low, :price_band_high, :lot_size, :issue_size,
    :open_date, :close_date, :allotment_date, :refund_date,
    :listing_date, :registrar, :status, :drhp_link
)
ON CONFLICT (symbol, exchange) DO UPDATE SET
    name = EXCLUDED.name,
    exchange_security_code = EXCLUDED.exchange_security_code,
    board = EXCLUDED.board,
    price_band_low = EXCLUDED.price_band_low,
    price_band_high = EXCLUDED.price_band_high,
    lot_size = EXCLUDED.lot_size,
    issue_size = EXCLUDED.issue_size,
    open_date = EXCLUDED.open_date,
    close_date = EXCLUDED.close_date,
    allotment_date = EXCLUDED.allotment_date,
    refund_date = EXCLUDED.refund_date,
    listing_date = EXCLUDED.listing_date,
    registrar = EXCLUDED.registrar,
    status = EXCLUDED.status,
    drhp_link = EXCLUDED.drhp_link
RETURNING id;
```

`issue_size` is denominated in INR crore. Prices are INR. Unknown or TBA IPO
details are stored as `NULL`; scrapers should distinguish an absent source field
from a confirmed empty field before overwriting an existing value.


`subscription_snapshots` and `raw_snapshots` are append-only. The database
rejects updates and deletes. Repeated delivery of the same subscription reading
is safely rejected by the `(ipo_id, captured_at, category)` unique constraint.

`listing_performance` has one row per IPO and may be upserted on `ipo_id`.
`listing_price_date` and `current_price_date` record which official EOD file
supplied each value. Never replace a current price with an older trading date.
`scraper_health` has one row per scheduled job and may be upserted on `name`.
`job_run_history` retains one row per scheduled job invocation so the daily
verification command can report actual successes, failures, and stuck runs
from the preceding 24 hours.
`watchdog_notifications` stores durable alert fingerprints and the daily digest
date so worker restarts do not resend unchanged alerts.

## Web app read access

`0005_web_readonly_role.sql` creates a `web_readonly` Postgres role with
`SELECT` only on `ipos`, `subscription_snapshots`, and `listing_performance`
— the tables a visitor-facing site needs. It has no access to
`raw_snapshots`, `scraper_health`, `job_run_history`, or
`watchdog_notifications`, and no write privileges anywhere, so a bug in the
web app can never corrupt data the worker owns. Apply it with a
generated password supplied out-of-band, never committed:

```powershell
psql "$env:DATABASE_URL" -v web_readonly_password="'<generated-password>'" -f 0005_web_readonly_role.sql
```

Put the resulting connection string in `web/.env` as `DATABASE_URL` (see
`web/.env.example`). The web app's Prisma schema (`web/prisma/schema.prisma`)
is a hand-maintained mirror of these three tables and must never be pointed
at `prisma migrate` against this database — migrations here are the worker's
responsibility.
