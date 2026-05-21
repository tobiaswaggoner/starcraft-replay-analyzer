"""FastAPI app with all endpoints. Single-file by intent — the API surface is small."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import get_conn, init_db
from .ingest import scan_folder
from .metrics import REGISTRY as METRIC_REGISTRY
from .recompute import recompute_all
from . import targets as targets_module
from .watcher import ReplayWatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
# sc2reader uses logger.error() for non-fatal "unknown unit/ability ID" messages
# whenever the current game build is newer than sc2reader's bundled data files.
# These don't break parsing — silence the whole family. Real parse failures still
# surface as exceptions caught in scan_folder/ingest_file.
logging.getLogger("sc2reader").setLevel(logging.CRITICAL)
log = logging.getLogger("sc2.api")

_watcher: ReplayWatcher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    global _watcher
    folder = settings.replay_dir_resolved
    if folder:
        _watcher = ReplayWatcher(folder)
        _watcher.start()
    yield
    if _watcher:
        _watcher.stop()


app = FastAPI(title="SC2 Replay Analyzer", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----- helpers -----

def _row_to_dict(row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _player_with_metrics(conn, player_row) -> dict[str, Any]:
    metrics = {
        r["metric_name"]: r["value"]
        for r in conn.execute(
            "SELECT metric_name, value FROM player_metrics WHERE player_id = ?",
            (player_row["id"],),
        )
    }
    p = _row_to_dict(player_row)
    p["metrics"] = metrics
    return p


def _compute_mode(players: list[dict]) -> str:
    humans = sum(1 for p in players if p.get("is_human"))
    if humans >= 2:
        return "PvP"
    if humans == 1:
        return "PvAI"
    return "AI"


def _player_count_label(players: list[dict]) -> str:
    n = len(players)
    if n == 2:
        return "1v1"
    return f"{n}p"


# ----- endpoints -----

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "replay_dir": str(settings.replay_dir_resolved) if settings.replay_dir_resolved else None,
        "db_path": str(settings.db_path_resolved),
    }


@app.get("/api/metrics")
def list_metrics() -> dict[str, Any]:
    return {"metrics": sorted(METRIC_REGISTRY.keys())}


@app.post("/api/ingest/scan")
def ingest_scan() -> dict[str, Any]:
    folder = settings.replay_dir_resolved
    if not folder or not folder.exists():
        raise HTTPException(400, f"REPLAY_DIR not configured or missing: {folder}")
    return scan_folder(folder)


@app.post("/api/ingest/recompute")
def ingest_recompute() -> dict[str, Any]:
    """Re-evaluate all metric functions on existing matches using stored timeseries."""
    return recompute_all()


# --- Targets ---

@app.get("/api/targets")
def list_targets() -> dict[str, Any]:
    with get_conn() as conn:
        return {"items": targets_module.list_targets(conn)}


@app.post("/api/targets")
def create_target(payload: targets_module.TargetIn) -> dict[str, Any]:
    if payload.metric_name not in METRIC_REGISTRY:
        raise HTTPException(400, f"Unknown metric: {payload.metric_name}")
    with get_conn() as conn:
        return targets_module.create_target(conn, payload)


@app.patch("/api/targets/{target_id}")
def update_target(target_id: int, payload: targets_module.TargetIn) -> dict[str, Any]:
    if payload.metric_name not in METRIC_REGISTRY:
        raise HTTPException(400, f"Unknown metric: {payload.metric_name}")
    with get_conn() as conn:
        updated = targets_module.update_target(conn, target_id, payload)
        if not updated:
            raise HTTPException(404, "Target not found")
        return updated


@app.delete("/api/targets/{target_id}")
def delete_target(target_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        if not targets_module.delete_target(conn, target_id):
            raise HTTPException(404, "Target not found")
    return {"ok": True}


@app.get("/api/matches")
def list_matches(
    limit: int = 200,
    offset: int = 0,
    matchup: str | None = None,
    race: str | None = None,
    result: str | None = None,
    map_name: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    where = []
    params: list[Any] = []
    if matchup:
        where.append("m.matchup = ?")
        params.append(matchup)
    if map_name:
        where.append("m.map_name = ?")
        params.append(map_name)
    if race or result:
        where.append("EXISTS (SELECT 1 FROM players p WHERE p.match_id = m.id"
                     + (" AND p.race = ?" if race else "")
                     + (" AND p.result = ?" if result else "")
                     + " AND p.is_me = 1)")
        if race:
            params.append(race)
        if result:
            params.append(result)

    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    sql = (
        "SELECT m.* FROM matches m"
        + sql_where
        + " ORDER BY m.played_at DESC LIMIT ? OFFSET ?"
    )
    params.extend([limit, offset])

    with get_conn() as conn:
        match_rows = list(conn.execute(sql, params))
        match_ids = [r["id"] for r in match_rows]
        players_by_match: dict[int, list[dict]] = {mid: [] for mid in match_ids}
        if match_ids:
            ph = ",".join("?" * len(match_ids))
            for row in conn.execute(
                f"SELECT * FROM players WHERE match_id IN ({ph}) ORDER BY player_index",
                match_ids,
            ):
                players_by_match[row["match_id"]].append(_player_with_metrics(conn, row))

        items = []
        for m in match_rows:
            d = _row_to_dict(m)
            players = players_by_match.get(m["id"], [])
            d["players"] = players
            d["mode"] = _compute_mode(players)
            d["player_count_label"] = _player_count_label(players)
            items.append(d)

        if mode:
            items = [it for it in items if it["mode"] == mode]

        total = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/matches/{match_id}")
def get_match(match_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        m = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        if not m:
            raise HTTPException(404, "Match not found")
        match = _row_to_dict(m)

        players = []
        for prow in conn.execute(
            "SELECT * FROM players WHERE match_id = ? ORDER BY player_index", (match_id,)
        ):
            p = _player_with_metrics(conn, prow)
            p["timeseries"] = [
                _row_to_dict(r) for r in conn.execute(
                    "SELECT game_time_seconds, workers, supply_used, supply_cap,"
                    " minerals_collected, gas_collected, army_value"
                    " FROM player_timeseries WHERE player_id = ? ORDER BY game_time_seconds",
                    (prow["id"],),
                )
            ]
            p["build_events"] = [
                _row_to_dict(r) for r in conn.execute(
                    "SELECT game_time_seconds, supply, event_type, name"
                    " FROM build_events WHERE player_id = ? ORDER BY game_time_seconds",
                    (prow["id"],),
                )
            ]
            players.append(p)

        match["players"] = players
        match["mode"] = _compute_mode(players)
        match["player_count_label"] = _player_count_label(players)

        # Evaluate all applicable training targets against the "me" player.
        me = next((p for p in players if p.get("is_me")), None) or next(
            (p for p in players if p.get("is_human")), None
        )
        all_targets = targets_module.list_targets(conn)
        evals = []
        for t in all_targets:
            if targets_module.applies_to(t, match, me):
                evals.append({"target": t, **targets_module.evaluate(t, me)})
        match["target_evaluations"] = evals
    return match


@app.get("/api/trends/{metric_name}")
def metric_trend(metric_name: str, race: str | None = None, matchup: str | None = None) -> dict[str, Any]:
    """Time-ordered values of a metric for 'me'. Optional filters."""
    if metric_name not in METRIC_REGISTRY:
        raise HTTPException(404, f"Unknown metric: {metric_name}")

    where = ["p.is_me = 1", "pm.metric_name = ?"]
    params: list[Any] = [metric_name]
    if race:
        where.append("p.race = ?")
        params.append(race)
    if matchup:
        where.append("m.matchup = ?")
        params.append(matchup)

    sql = (
        "SELECT m.id as match_id, m.played_at, m.map_name, m.matchup, p.result, pm.value"
        " FROM matches m"
        " JOIN players p ON p.match_id = m.id"
        " JOIN player_metrics pm ON pm.player_id = p.id"
        " WHERE " + " AND ".join(where)
        + " ORDER BY m.played_at"
    )
    with get_conn() as conn:
        points = [_row_to_dict(r) for r in conn.execute(sql, params)]
    return {"metric": metric_name, "points": points}


@app.get("/api/facets")
def facets() -> dict[str, Any]:
    """Distinct values for building filter dropdowns."""
    with get_conn() as conn:
        maps = [r[0] for r in conn.execute("SELECT DISTINCT map_name FROM matches ORDER BY map_name")]
        matchups = [r[0] for r in conn.execute(
            "SELECT DISTINCT matchup FROM matches WHERE matchup IS NOT NULL ORDER BY matchup"
        )]
    return {
        "maps": maps,
        "matchups": matchups,
        "races": ["Terran", "Zerg", "Protoss"],
        "results": ["Win", "Loss"],
        "modes": ["PvP", "PvAI", "AI"],
    }
