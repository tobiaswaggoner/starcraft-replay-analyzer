"""Ingest pipeline: parse a replay and write it to the DB.

Idempotent on file_hash — re-ingest with the same content is a no-op.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .config import settings
from .db import get_conn
from .metrics import compute_all
from .parser import ParsedReplay, parse_replay

log = logging.getLogger(__name__)


def _already_ingested(conn: sqlite3.Connection, file_hash: str) -> bool:
    row = conn.execute("SELECT 1 FROM matches WHERE file_hash = ?", (file_hash,)).fetchone()
    return row is not None


def ingest_file(path: Path) -> int | None:
    """Returns the match_id, or None if the file was already ingested."""
    parsed = parse_replay(path)
    with get_conn() as conn:
        if _already_ingested(conn, parsed.file_hash):
            log.info("Skipping %s (already ingested)", path.name)
            return None
        match_id = _insert(conn, parsed)
        log.info("Ingested %s as match_id=%s", path.name, match_id)

    # Auto-tag if enabled. Imported lazily to avoid circular import at module load.
    from . import app_settings, tagging
    if app_settings.get("auto_tag_on_ingest"):
        try:
            tagging.tag_match(match_id, retag=False)
        except Exception as e:
            log.warning("Auto-tag failed for match %s: %s", match_id, e)
    return match_id


def _insert(conn: sqlite3.Connection, parsed: ParsedReplay) -> int:
    cur = conn.execute(
        """
        INSERT INTO matches (
            file_hash, file_path, filename, played_at, duration_seconds,
            map_name, game_version, game_type, matchup, region, game_format
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            parsed.file_hash, parsed.file_path, parsed.filename, parsed.played_at,
            parsed.duration_seconds, parsed.map_name, parsed.game_version,
            parsed.game_type, parsed.matchup, parsed.region, parsed.game_format,
        ),
    )
    match_id = cur.lastrowid
    my_names = settings.my_names_set

    for pp in parsed.players:
        is_me = 1 if pp.name in my_names else 0
        cur = conn.execute(
            """
            INSERT INTO players (match_id, player_index, toon_handle, name, race, result, mmr, is_me, is_human, team)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (match_id, pp.player_index, pp.toon_handle, pp.name, pp.race, pp.result, pp.mmr, is_me, 1 if pp.is_human else 0, pp.team),
        )
        player_id = cur.lastrowid

        values = compute_all(pp, parsed)
        if values:
            conn.executemany(
                "INSERT INTO player_metrics (player_id, metric_name, value) VALUES (?, ?, ?)",
                [(player_id, k, v) for k, v in values.items()],
            )

        if pp.timeseries:
            conn.executemany(
                """
                INSERT INTO player_timeseries
                    (player_id, game_time_seconds, workers, supply_used, supply_cap,
                     minerals_collected, gas_collected, army_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        player_id, r["game_time_seconds"], r.get("workers"),
                        r.get("supply_used"), r.get("supply_cap"),
                        r.get("minerals_collected"), r.get("gas_collected"),
                        r.get("army_value"),
                    )
                    for r in pp.timeseries
                ],
            )

        if pp.build_events:
            conn.executemany(
                """
                INSERT INTO build_events (player_id, game_time_seconds, supply, event_type, name)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (player_id, e["game_time_seconds"], e.get("supply"), e["event_type"], e["name"])
                    for e in pp.build_events
                ],
            )

        if pp.apm_minutes:
            conn.executemany(
                "INSERT INTO player_apm_minutes (player_id, minute, apm) VALUES (?, ?, ?)",
                [(player_id, r["minute"], r["apm"]) for r in pp.apm_minutes],
            )

    return match_id


def scan_folder(folder: Path) -> dict[str, int]:
    """Walk the folder and ingest every .SC2Replay file. Returns counts."""
    seen = 0
    new = 0
    errors = 0
    for path in folder.rglob("*.SC2Replay"):
        seen += 1
        try:
            mid = ingest_file(path)
            if mid is not None:
                new += 1
        except Exception as e:
            errors += 1
            log.exception("Failed to ingest %s: %s", path, e)
    return {"seen": seen, "new": new, "errors": errors}
