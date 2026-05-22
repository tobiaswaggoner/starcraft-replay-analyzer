"""Recompute metrics on already-ingested matches without re-parsing replays.

Uses the timeseries data already in the DB. APM is preserved (sc2reader-derived,
not derivable from timeseries). All other metrics are re-evaluated from scratch.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import sc2reader

from .db import get_conn
from .metrics import REGISTRY, compute_all
from .parser import ParsedPlayer, ParsedReplay, compute_apm_total, compute_apm_minutes, derive_game_format

log = logging.getLogger(__name__)


def _empty_replay() -> ParsedReplay:
    return ParsedReplay(
        file_hash="", file_path="", filename="", played_at="",
        duration_seconds=0, map_name="", game_version=None, game_type=None,
        matchup=None, region=None, players=[],
    )


def recompute_all() -> dict:
    started = datetime.now()
    touched_players = 0
    metric_names = list(REGISTRY.keys())

    with get_conn() as conn:
        player_rows = list(conn.execute("SELECT id FROM players"))
        empty_replay = _empty_replay()

        for prow in player_rows:
            player_id = prow["id"]
            ts_rows = list(conn.execute(
                "SELECT game_time_seconds, workers, supply_used, supply_cap, "
                "minerals_collected, gas_collected, army_value "
                "FROM player_timeseries WHERE player_id = ? ORDER BY game_time_seconds",
                (player_id,),
            ))
            apm_row = conn.execute(
                "SELECT value FROM player_metrics WHERE player_id = ? AND metric_name = 'apm'",
                (player_id,),
            ).fetchone()
            apm = apm_row["value"] if apm_row else None

            stub = ParsedPlayer(
                player_index=0, toon_handle=None, name="", race="",
                result=None, mmr=None, apm=apm,
            )
            stub.timeseries = [dict(r) for r in ts_rows]

            values = compute_all(stub, empty_replay)

            # Replace only the metrics in REGISTRY; leave others alone if you
            # ever add manually-stored ones later.
            placeholders = ",".join("?" * len(metric_names))
            conn.execute(
                f"DELETE FROM player_metrics WHERE player_id = ? AND metric_name IN ({placeholders})",
                [player_id, *metric_names],
            )
            conn.executemany(
                "INSERT INTO player_metrics (player_id, metric_name, value) VALUES (?, ?, ?)",
                [(player_id, k, v) for k, v in values.items()],
            )
            touched_players += 1

    elapsed = (datetime.now() - started).total_seconds()
    log.info("Recomputed %d players in %.2fs", touched_players, elapsed)
    return {"players": touched_players, "metrics": metric_names, "elapsed_seconds": elapsed}


def reparse_apm() -> dict:
    """Open every replay file fresh and refresh just the APM metric per player.

    Needed because older sc2reader exposed avg_apm directly; the upstream branch
    no longer does, so old matches were ingested with APM=None. This endpoint
    re-derives APM from the replay's per-player event count without touching
    tags, timeseries, or any other data.
    """
    started = datetime.now()
    updated_players = 0
    matches_done = 0
    skipped_missing = 0
    errors = 0

    with get_conn() as conn:
        matches = list(conn.execute("SELECT id, file_path FROM matches"))

    for m in matches:
        path = Path(m["file_path"])
        if not path.exists():
            skipped_missing += 1
            continue
        try:
            replay = sc2reader.load_replay(str(path), load_level=4)
        except Exception as e:
            log.warning("reparse_apm: load failed for %s: %s", path, e)
            errors += 1
            continue

        duration = 0
        for attr in ("game_length", "length"):
            v = getattr(replay, attr, None)
            if v is not None:
                duration = getattr(v, "seconds", 0) or 0
                break

        player_team_human: list[tuple[int | None, bool]] = []
        with get_conn() as conn:
            for p in getattr(replay, "players", []) or []:
                apm = compute_apm_total(p, duration)
                buckets = compute_apm_minutes(p, duration)
                pid = getattr(p, "pid", 0) or 0
                player_row = conn.execute(
                    "SELECT id FROM players WHERE match_id = ? AND player_index = ?",
                    (m["id"], pid),
                ).fetchone()
                if not player_row:
                    continue
                player_id = player_row["id"]
                # Backfill team while we're here (same data, same cost).
                team_raw = getattr(p, "team_id", None) or getattr(p, "team", None)
                team_int: int | None = None
                try:
                    if team_raw is not None:
                        team_int = int(team_raw)
                except (TypeError, ValueError):
                    pass
                if team_int is not None:
                    conn.execute(
                        "UPDATE players SET team = ? WHERE id = ?",
                        (team_int, player_id),
                    )
                # Also refresh is_human from sc2reader's truth. Custom maps
                # name their AI 'Player 2' / 'Computer' etc., so the name
                # pattern fallback can't catch them — but the sc2reader
                # Computer class instance correctly has is_human=False.
                is_human = bool(getattr(p, "is_human", True)) and not (
                    (getattr(p, "name", "") or "").startswith("A.I.")
                )
                conn.execute(
                    "UPDATE players SET is_human = ? WHERE id = ?",
                    (1 if is_human else 0, player_id),
                )
                player_team_human.append((team_int, is_human))
                conn.execute(
                    """INSERT INTO player_metrics (player_id, metric_name, value)
                       VALUES (?, 'apm', ?)
                       ON CONFLICT(player_id, metric_name) DO UPDATE SET value = excluded.value""",
                    (player_id, apm),
                )
                conn.execute("DELETE FROM player_apm_minutes WHERE player_id = ?", (player_id,))
                if buckets:
                    conn.executemany(
                        "INSERT INTO player_apm_minutes (player_id, minute, apm) VALUES (?, ?, ?)",
                        [(player_id, r["minute"], r["apm"]) for r in buckets],
                    )
                updated_players += 1

            # Re-derive game_format from team membership + is_human. Without
            # team info the migration's heuristic stays in place; with team info
            # we now correctly distinguish 1v1 PvP from 2v2 PvP, and collapse
            # multi-team AI into a single opposition bucket (1v7 coop instead
            # of "1v1v1v1v1v1v1v1").
            fmt = derive_game_format(player_team_human)
            if fmt:
                conn.execute("UPDATE matches SET game_format = ? WHERE id = ?", (fmt, m["id"]))
        matches_done += 1

    elapsed = (datetime.now() - started).total_seconds()
    log.info("reparse_apm: %d matches, %d player metrics updated in %.2fs",
             matches_done, updated_players, elapsed)
    return {
        "matches": matches_done,
        "updated_players": updated_players,
        "skipped_missing_files": skipped_missing,
        "errors": errors,
        "elapsed_seconds": elapsed,
    }
