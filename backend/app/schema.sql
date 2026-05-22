PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash       TEXT NOT NULL UNIQUE,
    file_path       TEXT NOT NULL,
    filename        TEXT NOT NULL,
    played_at       TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    map_name        TEXT NOT NULL,
    game_version    TEXT,
    game_type       TEXT,
    matchup         TEXT,
    region          TEXT,
    game_format     TEXT,           -- '1v1', '2v2', '1v7', etc.
    ingested_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_matches_played_at ON matches(played_at DESC);
CREATE INDEX IF NOT EXISTS idx_matches_matchup ON matches(matchup);

CREATE TABLE IF NOT EXISTS players (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_index    INTEGER NOT NULL,
    toon_handle     TEXT,
    name            TEXT NOT NULL,
    race            TEXT NOT NULL,
    result          TEXT,
    mmr             INTEGER,
    is_me           INTEGER NOT NULL DEFAULT 0,
    is_human        INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_players_match ON players(match_id);
CREATE INDEX IF NOT EXISTS idx_players_is_me ON players(is_me);

CREATE TABLE IF NOT EXISTS player_metrics (
    player_id   INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    value       REAL,
    PRIMARY KEY (player_id, metric_name)
);

CREATE TABLE IF NOT EXISTS build_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id           INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    game_time_seconds   REAL NOT NULL,
    supply              INTEGER,
    event_type          TEXT NOT NULL,
    name                TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_build_events_player ON build_events(player_id, game_time_seconds);

-- App-level config persisted in DB (so it's UI-editable).
CREATE TABLE IF NOT EXISTS app_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

-- Tag vocabulary. Seeded from tags_seed.yaml; can be edited/extended via UI.
CREATE TABLE IF NOT EXISTS tags (
    slug              TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    category          TEXT NOT NULL,
    description       TEXT,
    applies_to_races  TEXT,            -- JSON array of races; NULL = any
    color             TEXT,
    created_by        TEXT NOT NULL,   -- 'system' | 'user'
    created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Tags assigned to individual players in individual matches.
CREATE TABLE IF NOT EXISTS player_tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    tag_slug    TEXT    NOT NULL REFERENCES tags(slug) ON DELETE CASCADE,
    source      TEXT    NOT NULL,        -- 'llm' | 'manual'
    confidence  REAL,
    reasoning   TEXT,
    model       TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (player_id, tag_slug, source)
);

CREATE INDEX IF NOT EXISTS idx_player_tags_player ON player_tags(player_id);
CREATE INDEX IF NOT EXISTS idx_player_tags_slug ON player_tags(tag_slug);

-- One row per match captures the LLM's per-match summary + bookkeeping.
CREATE TABLE IF NOT EXISTS tagging_runs (
    match_id        INTEGER PRIMARY KEY REFERENCES matches(id) ON DELETE CASCADE,
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    match_summary   TEXT,
    raw_response    TEXT,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS training_targets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    metric_name  TEXT NOT NULL,
    operator     TEXT NOT NULL,        -- '>=', '<=', '=='
    threshold    REAL NOT NULL,
    race         TEXT,                  -- nullable filter (any)
    matchup      TEXT,                  -- nullable filter
    mode         TEXT,                  -- nullable filter ('PvP' / 'PvAI')
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS player_timeseries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id           INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    game_time_seconds   REAL NOT NULL,
    workers             INTEGER,
    supply_used         INTEGER,
    supply_cap          INTEGER,
    minerals_collected  INTEGER,
    gas_collected       INTEGER,
    army_value          INTEGER
);

CREATE INDEX IF NOT EXISTS idx_timeseries_player ON player_timeseries(player_id, game_time_seconds);
