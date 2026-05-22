"""FastAPI app with all endpoints. Single-file by intent — the API surface is small."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from .config import settings
from .db import get_conn, init_db
from .ingest import scan_folder
from .metrics import REGISTRY as METRIC_REGISTRY
from .recompute import recompute_all, reparse_apm
from . import targets as targets_module
from . import app_settings as app_settings_module
from . import tags_vocab
from . import tagging
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
    with get_conn() as conn:
        n = tags_vocab.seed_if_empty(conn)
        if n:
            log.info("Seeded %d tags from YAML", n)
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


def _player_with_metrics(conn, player_row, include_tags: bool = True) -> dict[str, Any]:
    metrics = {
        r["metric_name"]: r["value"]
        for r in conn.execute(
            "SELECT metric_name, value FROM player_metrics WHERE player_id = ?",
            (player_row["id"],),
        )
    }
    p = _row_to_dict(player_row)
    p["metrics"] = metrics
    if include_tags:
        p["tags"] = [
            _row_to_dict(r) for r in conn.execute(
                """SELECT pt.tag_slug, pt.source, pt.confidence, pt.reasoning, pt.model,
                          t.name, t.category, t.color
                   FROM player_tags pt JOIN tags t ON t.slug = pt.tag_slug
                   WHERE pt.player_id = ?
                   ORDER BY pt.source = 'llm' DESC, COALESCE(pt.confidence, -1) DESC""",
                (player_row["id"],),
            )
        ]
    return p


def _compute_mode(players: list[dict]) -> str:
    humans = [p for p in players if p.get("is_human")]
    if not humans:
        return "AI"
    if len(humans) == 1:
        return "PvAI"
    # Multiple humans. PvP requires at least one human on a different team
    # than another human. Otherwise it's a coop game (PvAI) even with two+
    # humans (e.g. 2v2 vs AI).
    teams = {p.get("team") for p in humans if p.get("team") is not None}
    if len(teams) >= 2:
        return "PvP"
    if len(teams) == 1:
        return "PvAI"
    # No team info recorded — conservative default for legacy data.
    return "PvP"


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


@app.post("/api/ingest/reparse-apm")
def ingest_reparse_apm() -> dict[str, Any]:
    """Re-open each replay file and refresh just the APM metric per player.
    Use this after the parser's APM logic changes — no other data is touched."""
    return reparse_apm()


# --- App settings (UI-editable runtime config) ---

class SettingsPatch(BaseModel):
    openrouter_api_key: str | None = None
    tagging_model: str | None = None
    auto_tag_on_ingest: bool | None = None


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    s = app_settings_module.get_public_view()
    s["available_models"] = app_settings_module.AVAILABLE_MODELS
    return s


@app.patch("/api/settings")
def patch_settings(payload: SettingsPatch) -> dict[str, Any]:
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    app_settings_module.set_many(updates)
    return get_settings()


@app.post("/api/settings/test-connection")
def settings_test_connection() -> dict[str, Any]:
    return tagging.test_connection()


# --- Tag vocabulary ---

@app.get("/api/tags")
def list_tags() -> dict[str, Any]:
    with get_conn() as conn:
        return {"items": tags_vocab.list_all(conn)}


@app.post("/api/tags")
def create_tag(payload: tags_vocab.TagCreate) -> dict[str, Any]:
    with get_conn() as conn:
        existing = tags_vocab.get_one(conn, payload.slug)
        if existing:
            raise HTTPException(409, f"Tag '{payload.slug}' already exists")
        return tags_vocab.create(conn, payload)


@app.patch("/api/tags/{slug}")
def update_tag(slug: str, payload: tags_vocab.TagIn) -> dict[str, Any]:
    with get_conn() as conn:
        updated = tags_vocab.update(conn, slug, payload)
        if not updated:
            raise HTTPException(404, "Tag not found")
        return updated


@app.delete("/api/tags/{slug}")
def delete_tag(slug: str) -> dict[str, Any]:
    with get_conn() as conn:
        if not tags_vocab.delete(conn, slug):
            raise HTTPException(404, "Tag not found")
    return {"ok": True}


@app.post("/api/tags/reset-seed")
def reset_seed_tags() -> dict[str, Any]:
    with get_conn() as conn:
        n = tags_vocab.reset_seed(conn)
    return {"imported": n}


# --- LLM tagging ---

@app.post("/api/matches/{match_id}/tag")
def tag_match_endpoint(match_id: int, retag: bool = False) -> dict[str, Any]:
    try:
        return tagging.tag_match(match_id, retag=retag)
    except tagging.LLMError as e:
        raise HTTPException(400, str(e))


@app.post("/api/tagging/run")
def run_batch_tagging(limit: int | None = None) -> dict[str, Any]:
    return tagging.tag_untagged(limit=limit)


class ManualTagPayload(BaseModel):
    tag_slug: str


@app.post("/api/players/{player_id}/tags")
def add_player_tag(player_id: int, payload: ManualTagPayload) -> dict[str, Any]:
    try:
        return tagging.add_manual_tag(player_id, payload.tag_slug)
    except tagging.LLMError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/players/{player_id}/tags/{tag_slug}")
def remove_player_tag(player_id: int, tag_slug: str, source: str = "manual") -> dict[str, Any]:
    ok = tagging.remove_player_tag(player_id, tag_slug, source)
    if not ok:
        raise HTTPException(404, "Player tag not found")
    return {"ok": True}


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
    limit: int = 10000,
    offset: int = 0,
    matchup: str | None = None,
    race: str | None = None,
    result: str | None = None,
    map_name: str | None = None,
    mode: str | None = None,
    tag: str | None = None,
    game_format: str | None = None,
    include_invalid: bool = False,
) -> dict[str, Any]:
    where = []
    params: list[Any] = []
    # Drop '1v0' single-player custom games (user-confirmed: aborted custom
    # lobbies with no opponent that ended on game start). Toggle via
    # include_invalid=true if you ever need to see them.
    if not include_invalid:
        where.append("(m.game_format IS NULL OR m.game_format != '1v0')")
    if matchup:
        where.append("m.matchup = ?")
        params.append(matchup)
    if map_name:
        where.append("m.map_name = ?")
        params.append(map_name)
    if game_format:
        where.append("m.game_format = ?")
        params.append(game_format)
    if race or result:
        where.append("EXISTS (SELECT 1 FROM players p WHERE p.match_id = m.id"
                     + (" AND p.race = ?" if race else "")
                     + (" AND p.result = ?" if result else "")
                     + " AND p.is_me = 1)")
        if race:
            params.append(race)
        if result:
            params.append(result)
    if tag:
        # Filter on the "me" player having the given tag (any source).
        where.append("EXISTS (SELECT 1 FROM players p JOIN player_tags pt ON pt.player_id = p.id "
                     "WHERE p.match_id = m.id AND p.is_me = 1 AND pt.tag_slug = ?)")
        params.append(tag)
    # Mode filter has to live in SQL (not post-filtering) so it applies BEFORE
    # the LIMIT/OFFSET pagination — otherwise rare modes (e.g. PvP when most
    # matches are PvAI) silently fall off the first page.
    if mode == "PvP":
        where.append(
            "EXISTS (SELECT 1 FROM players p WHERE p.match_id = m.id AND p.is_human = 1"
            " GROUP BY p.match_id HAVING COUNT(DISTINCT p.team) >= 2)"
        )
    elif mode == "PvAI":
        where.append("EXISTS (SELECT 1 FROM players p WHERE p.match_id = m.id AND p.is_human = 1)")
        where.append(
            "NOT EXISTS (SELECT 1 FROM players p WHERE p.match_id = m.id AND p.is_human = 1"
            " GROUP BY p.match_id HAVING COUNT(DISTINCT p.team) >= 2)"
        )
    elif mode == "AI":
        where.append(
            "NOT EXISTS (SELECT 1 FROM players p WHERE p.match_id = m.id AND p.is_human = 1)"
        )

    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    where_params = list(params)  # for the COUNT query
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

        # Total reflects the filtered set, not the whole DB — so the UI
        # winrate/count line stays consistent with what the user is seeing.
        count_sql = "SELECT COUNT(*) FROM matches m" + sql_where
        total = conn.execute(count_sql, where_params).fetchone()[0]

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
            p["apm_minutes"] = [
                _row_to_dict(r) for r in conn.execute(
                    "SELECT minute, apm FROM player_apm_minutes WHERE player_id = ? ORDER BY minute",
                    (prow["id"],),
                )
            ]
            players.append(p)

        match["players"] = players
        match["mode"] = _compute_mode(players)
        match["player_count_label"] = _player_count_label(players)

        run = conn.execute(
            "SELECT model, prompt_version, match_summary, created_at FROM tagging_runs WHERE match_id = ?",
            (match_id,),
        ).fetchone()
        match["tagging_run"] = _row_to_dict(run) if run else None

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
        game_formats = [r[0] for r in conn.execute(
            "SELECT DISTINCT game_format FROM matches"
            " WHERE game_format IS NOT NULL AND game_format != '1v0'"
            " ORDER BY game_format"
        )]
        tags = [
            _row_to_dict(r) for r in conn.execute(
                """SELECT t.slug, t.name, t.category, t.color,
                          COUNT(CASE WHEN p.is_me = 1 THEN 1 END) AS usage_count
                   FROM tags t
                   LEFT JOIN player_tags pt ON pt.tag_slug = t.slug
                   LEFT JOIN players p ON p.id = pt.player_id
                   GROUP BY t.slug ORDER BY t.category, t.name"""
            )
        ]
    return {
        "maps": maps,
        "matchups": matchups,
        "game_formats": game_formats,
        "races": ["Terran", "Zerg", "Protoss"],
        "results": ["Win", "Loss"],
        "modes": ["PvP", "PvAI", "AI"],
        "tags": tags,
    }
