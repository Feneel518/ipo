BEGIN;

ALTER TABLE ipos
ADD COLUMN exchange_security_code TEXT;

ALTER TABLE ipos
ADD CONSTRAINT ipos_exchange_security_code_clean CHECK (
    exchange_security_code IS NULL
    OR exchange_security_code = upper(btrim(exchange_security_code))
);

CREATE UNIQUE INDEX ipos_exchange_security_code_key
ON ipos (exchange, exchange_security_code)
WHERE exchange_security_code IS NOT NULL;

COMMENT ON COLUMN ipos.exchange_security_code IS
    'Exchange instrument identifier; required to match legacy BSE bhavcopies';

ALTER TABLE listing_performance
ADD COLUMN listing_price_date DATE,
ADD COLUMN current_price_date DATE;

COMMENT ON COLUMN listing_performance.listing_price_date IS
    'Trading date of the EOD file used for listing open and close';
COMMENT ON COLUMN listing_performance.current_price_date IS
    'Trading date of the EOD file used for current_price';

COMMIT;
