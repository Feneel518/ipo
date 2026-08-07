BEGIN;

CREATE TABLE job_run_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL CHECK (btrim(name) <> ''),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'succeeded', 'failed')),
    error TEXT,
    CONSTRAINT job_run_history_terminal_state CHECK (
        (status = 'running' AND finished_at IS NULL)
        OR (status IN ('succeeded', 'failed') AND finished_at IS NOT NULL)
    )
);

CREATE INDEX job_run_history_started_at_idx
ON job_run_history (started_at DESC);

CREATE INDEX job_run_history_name_started_at_idx
ON job_run_history (name, started_at DESC);

COMMENT ON TABLE job_run_history IS
    'One row per scheduled job run, retained for burn-in verification';

COMMIT;
