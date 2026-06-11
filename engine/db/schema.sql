-- The Untold Game — schema (idea → video → metrics). The JSON queue is today's
-- store; this is the Stage-3 target when the learning loop needs SQL.
CREATE TABLE IF NOT EXISTS ideas (
    id           TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    source_agent TEXT NOT NULL,        -- sports_history | trending_topics | competitor_gap | evergreen
    pillar       TEXT,
    sport        TEXT,
    title        TEXT,
    hook         TEXT,
    viral_score  REAL,
    status       TEXT NOT NULL DEFAULT 'pending'  -- pending|approved|rejected|scripted|scheduled|published
);
CREATE TABLE IF NOT EXISTS videos (
    id           TEXT PRIMARY KEY,
    idea_id      TEXT REFERENCES ideas(id),
    youtube_id   TEXT,
    published_at TEXT,
    title        TEXT
);
CREATE TABLE IF NOT EXISTS metrics (
    video_id     TEXT REFERENCES videos(id),
    as_of        TEXT NOT NULL,
    views        INTEGER,
    ctr          REAL,
    avg_view_pct REAL,
    PRIMARY KEY (video_id, as_of)
);
