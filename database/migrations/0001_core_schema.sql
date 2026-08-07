BEGIN;

CREATE TABLE ipos (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL CHECK (btrim(name) <> ''),
    symbol TEXT NOT NULL CHECK (
        btrim(symbol) <> '' AND symbol = upper(btrim(symbol))
    ),
    exchange TEXT NOT NULL CHECK (
        btrim(exchange) <> '' AND exchange = upper(btrim(exchange))
    ),
    board TEXT NOT NULL CHECK (board IN ('mainboard', 'SME')),
    price_band_low NUMERIC(12, 2) CHECK (price_band_low > 0),
    price_band_high NUMERIC(12, 2) CHECK (price_band_high > 0),
    lot_size INTEGER CHECK (lot_size > 0),
    -- Amount in INR crore. Keeping the unit explicit prevents scraper ambiguity.
    issue_size NUMERIC(14, 2) CHECK (issue_size > 0),
    open_date DATE,
    close_date DATE,
    allotment_date DATE,
    refund_date DATE,
    listing_date DATE,
    registrar TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('upcoming', 'open', 'closed', 'allotted', 'listed')
    ),
    drhp_link TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ipos_price_band_order CHECK (
        price_band_low IS NULL
        OR price_band_high IS NULL
        OR price_band_low <= price_band_high
    ),
    CONSTRAINT ipos_symbol_exchange_key UNIQUE (symbol, exchange)
);

COMMENT ON COLUMN ipos.issue_size IS 'Total issue size in INR crore';
COMMENT ON CONSTRAINT ipos_symbol_exchange_key ON ipos IS
    'Natural key used by all IPO detail scraper upserts';

CREATE TABLE subscription_snapshots (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ipo_id BIGINT NOT NULL REFERENCES ipos (id) ON DELETE RESTRICT,
    captured_at TIMESTAMPTZ NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('QIB', 'NII', 'retail', 'total')),
    subscription_multiple NUMERIC(14, 4) NOT NULL
        CHECK (subscription_multiple >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT subscription_snapshot_observation_key
        UNIQUE (ipo_id, captured_at, category)
);

COMMENT ON TABLE subscription_snapshots IS
    'Append-only time series of category-level IPO subscriptions';

CREATE TABLE listing_performance (
    ipo_id BIGINT PRIMARY KEY REFERENCES ipos (id) ON DELETE RESTRICT,
    listing_open_price NUMERIC(12, 2) CHECK (listing_open_price >= 0),
    listing_close_price NUMERIC(12, 2) CHECK (listing_close_price >= 0),
    current_price NUMERIC(12, 2) CHECK (current_price >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scraper_health (
    name TEXT PRIMARY KEY CHECK (btrim(name) <> ''),
    last_run TIMESTAMPTZ,
    last_success TIMESTAMPTZ,
    last_error TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0
        CHECK (consecutive_failures >= 0)
);

CREATE TABLE raw_snapshots (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scraper_name TEXT NOT NULL CHECK (btrim(scraper_name) <> ''),
    captured_at TIMESTAMPTZ NOT NULL,
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE raw_snapshots IS
    'Append-only source payloads retained for parser replay and debugging';

CREATE INDEX ipos_status_open_date_idx ON ipos (status, open_date);
CREATE INDEX ipos_listing_date_idx ON ipos (listing_date);
CREATE INDEX subscription_snapshots_ipo_captured_idx
    ON subscription_snapshots (ipo_id, captured_at DESC);
CREATE INDEX raw_snapshots_scraper_captured_idx
    ON raw_snapshots (scraper_name, captured_at DESC);

CREATE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER ipos_set_updated_at
BEFORE UPDATE ON ipos
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER listing_performance_set_updated_at
BEFORE UPDATE ON listing_performance
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE FUNCTION reject_append_only_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only; % is not allowed', TG_TABLE_NAME, TG_OP;
END;
$$;

CREATE TRIGGER subscription_snapshots_append_only
BEFORE UPDATE OR DELETE ON subscription_snapshots
FOR EACH ROW
EXECUTE FUNCTION reject_append_only_change();

CREATE TRIGGER raw_snapshots_append_only
BEFORE UPDATE OR DELETE ON raw_snapshots
FOR EACH ROW
EXECUTE FUNCTION reject_append_only_change();

COMMIT;
