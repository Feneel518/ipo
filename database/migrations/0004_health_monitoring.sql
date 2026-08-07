BEGIN;

CREATE TABLE watchdog_notifications (
    notification_key TEXT PRIMARY KEY CHECK (btrim(notification_key) <> ''),
    fingerprint TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE watchdog_notifications IS
    'Durable Telegram deduplication and daily watchdog heartbeat state';

COMMIT;
