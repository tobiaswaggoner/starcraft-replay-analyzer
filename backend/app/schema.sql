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
