import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import settings

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _connect() -> sqlite3.Connection:
    db_path = settings.db_path_resolved
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate(conn)
        conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """One-shot migrations for older schema versions."""
    # is_human column on players (added after first walking-skeleton release).
    player_cols = {c["name"] for c in conn.execute("PRAGMA table_info(players)")}
    if player_cols and "is_human" not in player_cols:
        conn.execute("ALTER TABLE players ADD COLUMN is_human INTEGER NOT NULL DEFAULT 1")
    # Team membership column (added for correct PvP/PvAI/Coop classification).
    if player_cols and "team" not in player_cols:
        conn.execute("ALTER TABLE players ADD COLUMN team INTEGER")
    # Idempotent: reclassify AI-named players whose is_human flag is still default.
    # Cheap to run on every startup; only updates rows that match the AI name pattern.
    conn.execute("UPDATE players SET is_human = 0 WHERE is_human = 1 AND name LIKE 'A.I.%'")

    # game_format column on matches (added with the tagging feature).
    match_cols = {c["name"] for c in conn.execute("PRAGMA table_info(matches)")}
    if match_cols and "game_format" not in match_cols:
        conn.execute("ALTER TABLE matches ADD COLUMN game_format TEXT")
    # Backfill game_format for any rows still NULL: derive humans-vs-AI count.
    # (Proper team-based detection happens at ingest time for new replays.)
    conn.executescript(
        """
        UPDATE matches
        SET game_format = (
            WITH counts AS (
                SELECT match_id,
                       SUM(CASE WHEN is_human = 1 THEN 1 ELSE 0 END) AS humans,
                       SUM(CASE WHEN is_human = 0 THEN 1 ELSE 0 END) AS ai
                FROM players
                GROUP BY match_id
            )
            SELECT
                CASE
                    WHEN c.ai = 0 THEN CAST(c.humans AS TEXT) || 'v' || CAST(c.humans AS TEXT)
                    WHEN c.humans = 0 THEN CAST(c.ai AS TEXT) || 'v' || CAST(c.ai AS TEXT)
                    ELSE CAST(c.humans AS TEXT) || 'v' || CAST(c.ai AS TEXT)
                END
            FROM counts c WHERE c.match_id = matches.id
        )
        WHERE game_format IS NULL;
        """
    )

    cols = conn.execute("PRAGMA table_info(player_timeseries)").fetchall()
    has_id = any(c["name"] == "id" for c in cols)
    if cols and not has_id:
        conn.executescript(
            """
            ALTER TABLE player_timeseries RENAME TO player_timeseries_old;
            CREATE TABLE player_timeseries (
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
            INSERT INTO player_timeseries (player_id, game_time_seconds, workers, supply_used,
                supply_cap, minerals_collected, gas_collected, army_value)
            SELECT player_id, game_time_seconds, workers, supply_used, supply_cap,
                minerals_collected, gas_collected, army_value FROM player_timeseries_old;
            DROP TABLE player_timeseries_old;
            CREATE INDEX IF NOT EXISTS idx_timeseries_player
                ON player_timeseries(player_id, game_time_seconds);
            """
        )


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
