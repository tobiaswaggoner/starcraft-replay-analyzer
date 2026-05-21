"""Recompute metrics on already-ingested matches without re-parsing replays.

Uses the timeseries data already in the DB. APM is preserved (sc2reader-derived,
not derivable from timeseries). All other metrics are re-evaluated from scratch.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .db import get_conn
from .metrics import REGISTRY, compute_all
from .parser import ParsedPlayer, ParsedReplay

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
