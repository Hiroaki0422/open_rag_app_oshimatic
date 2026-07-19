CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    manifest_uri TEXT NOT NULL,
    manifest_checksum TEXT NOT NULL,
    manifest_media_type TEXT NOT NULL,
    manifest_byte_length INTEGER NOT NULL,
    trace_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_expires_at TEXT,
    failure_reason_code TEXT,
    metadata_json TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    UNIQUE (run_type, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

