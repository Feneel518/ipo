BEGIN;

-- Least-privilege role for the Next.js web app. It reads the public IPO
-- catalog directly from Postgres and must never be able to write, so it
-- gets SELECT on exactly the tables a visitor-facing site needs and nothing
-- on worker-internal tables (raw_snapshots, scraper_health, job_run_history,
-- watchdog_notifications).
--
-- Run with the password supplied out-of-band, e.g.:
--   psql "$DATABASE_URL" -v web_readonly_password="'<generated-password>'" -f 0005_web_readonly_role.sql
CREATE ROLE web_readonly LOGIN PASSWORD :'web_readonly_password';

DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO web_readonly', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO web_readonly;

GRANT SELECT ON ipos TO web_readonly;
GRANT SELECT ON subscription_snapshots TO web_readonly;
GRANT SELECT ON listing_performance TO web_readonly;

COMMENT ON ROLE web_readonly IS
    'Read-only role for the Next.js web app; SELECT-only on public-facing IPO tables';

COMMIT;
