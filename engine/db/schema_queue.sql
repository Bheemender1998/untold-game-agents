-- The Untold Game — shared queue schema (Neon). Document-in-Postgres: promoted
-- columns for the queries queue_manager runs + the full idea dict in `data`.
CREATE TABLE IF NOT EXISTS ideas (
    id           TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'pending',
    viral_score  REAL,
    source_agent TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    data         JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ideas_status_score ON ideas (status, viral_score DESC);

-- Durable cost ledger (Railway fs is ephemeral; the monthly cap reads this).
CREATE TABLE IF NOT EXISTS api_costs (
    id      BIGSERIAL PRIMARY KEY,
    ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
    agent   TEXT,
    run_id  TEXT,
    usd     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS api_costs_ts ON api_costs (ts);
