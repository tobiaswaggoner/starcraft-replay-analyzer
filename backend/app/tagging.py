"""LLM-driven multi-label tagging of players in a match.

One LLM call per match returns tags for every player. Uses LiteLLM as the
transport so the underlying model can be swapped via app_settings.

The prompt version is bumped whenever the prompt structure or instructions
change; persisted in `tagging_runs.prompt_version` for traceability.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from . import app_settings, tags_vocab
from .db import get_conn

log = logging.getLogger(__name__)

PROMPT_VERSION = "v1"


class TagAssignment(BaseModel):
    tag_slug: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class PlayerTagging(BaseModel):
    player_index: int
    tags: list[TagAssignment]


class MatchTaggingResponse(BaseModel):
    players: list[PlayerTagging]
    match_summary: str


# --- Prompt building ---

def _player_block(player: dict, build_window_seconds: int = 300) -> str:
    metrics = player.get("metrics", {})
    metric_lines = ", ".join(
        f"{k}={_fmt(v)}" for k, v in metrics.items() if v is not None
    ) or "none"
    events = player.get("build_events", [])
    # Skip events at second 0 — these are starting units (12 workers, the
    # main base, etc.) the player did not actually build. Including them
    # leads the LLM to spurious tags like "Nexus First".
    events = [
        e for e in events
        if e["game_time_seconds"] > 0 and e["game_time_seconds"] <= build_window_seconds
    ]
    bo = ", ".join(
        f"{_fmt_time(e['game_time_seconds'])} {e['name']}"
        + (f" ({e['supply']})" if e.get("supply") is not None else "")
        for e in events[:60]
    ) or "(no events in first 5 min)"
    team = player.get("team")
    team_str = f", team {team}" if team is not None else ""
    return (
        f"Player {player['player_index']} — {player['name']} ({player['race']}, "
        f"{'AI' if not player.get('is_human') else 'human'}{team_str}, "
        f"result={player.get('result') or '?'})\n"
        f"  Metrics: {metric_lines}\n"
        f"  Build (first {build_window_seconds//60} min, starting units excluded): {bo}"
    )


def _vocab_block(all_tags: list[dict]) -> str:
    by_cat: dict[str, list[dict]] = {}
    for t in all_tags:
        by_cat.setdefault(t["category"], []).append(t)
    lines: list[str] = []
    for cat in ("strategy", "tech", "build", "tempo", "outcome"):
        cat_tags = by_cat.get(cat, [])
        if not cat_tags:
            continue
        lines.append(f"\n  [{cat.upper()}]")
        for t in cat_tags:
            races = t.get("applies_to_races") or "any race"
            races_str = ",".join(races) if isinstance(races, list) else races
            desc = (t.get("description") or "").replace("\n", " ").strip()
            lines.append(f"    - {t['slug']} ({races_str}): {desc}")
    return "\n".join(lines)


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def _fmt_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def build_prompt(match: dict, players: list[dict], vocab: list[dict]) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt)."""
    from .parser import derive_mode

    mode = derive_mode([(p.get("team"), bool(p.get("is_human"))) for p in players])

    system = (
        "You are a StarCraft 2 replay analyst. You classify each player's strategy "
        "in a single match using a controlled tag vocabulary. You always respond "
        "with valid JSON matching the requested schema — no markdown, no code "
        "fences, no commentary outside the JSON object. You only use tag slugs "
        "from the provided vocabulary. You assign confidence in [0,1]. Reasoning "
        "is one short sentence citing concrete evidence from the build order or "
        "metrics. Prefer fewer, high-quality tags over many speculative ones — "
        "typically 2–5 tags per player across categories (strategy, tech, build, "
        "tempo, outcome). If the game ended very early or you have insufficient "
        "evidence, return the 'gg-out-early' tag only.\n\n"
        "Important: the build order lists events that occurred AFTER game start. "
        "Every player begins with their main base building and ~12 workers — do "
        "NOT infer 'nexus-first', 'cc-first', or 'hatch-first' from those; only "
        "tag those builds if the player BUILDS A NEW main-base building before "
        "any production structure. Also: AI opponents in custom maps may use "
        "trivially predictable behaviour; tag conservatively for them."
    )

    duration_s = match.get("duration_seconds", 0) or 0
    duration_str = f"{duration_s // 60}:{duration_s % 60:02d}"

    player_blocks = "\n\n".join(_player_block(p) for p in players)

    team_layout = ", ".join(
        f"P{p['player_index']}({p.get('race', '?')}, "
        f"{'AI' if not p.get('is_human') else 'human'}, team {p.get('team', '?')})"
        for p in players
    )

    user = (
        f"Match context:\n"
        f"  Map: {match.get('map_name')}\n"
        f"  Mode: {mode} ({match.get('game_format') or '?'})\n"
        f"  Matchup: {match.get('matchup') or 'n/a'}\n"
        f"  Duration: {duration_str}\n"
        f"  Game version: {match.get('game_version') or '?'}\n"
        f"  Players: {team_layout}\n\n"
        f"Vocabulary (slug — applicable races — description):\n{_vocab_block(vocab)}\n\n"
        f"Players:\n\n{player_blocks}\n\n"
        "Return JSON with this exact shape:\n"
        "{\n"
        '  "match_summary": "one-sentence overall description of the match",\n'
        '  "players": [\n'
        '    {"player_index": 1, "tags": [\n'
        '       {"tag_slug": "...", "confidence": 0.0-1.0, "reasoning": "..."},\n'
        "       ...\n"
        "    ]},\n"
        "    ...\n"
        "  ]\n"
        "}\n"
        "Only use tag slugs from the vocabulary. Reasoning must be concrete (cite a "
        "time, building, or metric)."
    )
    return system, user


# --- LLM call ---

class LLMError(Exception):
    pass


def _strip_code_fence(text: str) -> str:
    """Some models wrap JSON in ```json ... ``` fences despite response_format hints."""
    t = text.strip()
    if t.startswith("```"):
        # Remove opening fence (with optional language tag) and trailing fence
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1:]
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()
    return t


def _parse_llm_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Retry after stripping a code fence.
        stripped = _strip_code_fence(content)
        if stripped != content:
            return json.loads(stripped)
        raise


def call_llm(system: str, user: str, model: str, api_key: str) -> dict:
    if not api_key:
        raise LLMError("OpenRouter API key not configured. Set it in Settings.")

    # LiteLLM picks up provider from the slash prefix; for OpenRouter we use the
    # 'openrouter/' prefix on the model id.
    from litellm import completion

    os.environ["OPENROUTER_API_KEY"] = api_key

    or_model = model if model.startswith("openrouter/") else f"openrouter/{model}"
    try:
        resp = completion(
            model=or_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            # 8-player matches with 3–5 tags per player + reasoning can be large;
            # leave room so the response is never truncated mid-JSON.
            max_tokens=8000,
        )
    except Exception as e:
        raise LLMError(f"{type(e).__name__}: {e}") from e

    finish_reason = resp["choices"][0].get("finish_reason")
    content = resp["choices"][0]["message"]["content"]
    if not content:
        raise LLMError("LLM returned empty content")

    try:
        parsed = _parse_llm_json(content)
    except json.JSONDecodeError as e:
        truncated_hint = " (response truncated by max_tokens)" if finish_reason == "length" else ""
        raise LLMError(
            f"LLM returned non-JSON{truncated_hint}: {e}; finish={finish_reason}; "
            f"raw[:800]={content[:800]}"
        ) from e
    return parsed


# --- Tagging orchestration ---

def tag_match(match_id: int, retag: bool = False) -> dict[str, Any]:
    """Tag every player in a match. Returns a summary dict.

    If retag=False and the match is already tagged (has a tagging_runs row),
    returns early with status='cached'. retag=True forces a fresh call and
    replaces all source='llm' player_tags.
    """
    settings = app_settings.get_all()
    api_key = settings.get("openrouter_api_key", "")
    model = settings.get("tagging_model", "anthropic/claude-haiku-4.5")

    with get_conn() as conn:
        run = conn.execute(
            "SELECT model, prompt_version FROM tagging_runs WHERE match_id = ?",
            (match_id,),
        ).fetchone()
        if run and not retag:
            return {"status": "cached", "match_id": match_id, "model": run["model"]}

        match_row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        if not match_row:
            raise LLMError(f"Match {match_id} not found")
        match = dict(match_row)

        player_rows = list(conn.execute(
            "SELECT * FROM players WHERE match_id = ? ORDER BY player_index", (match_id,)
        ))
        players: list[dict] = []
        for prow in player_rows:
            p = dict(prow)
            p["metrics"] = {
                r["metric_name"]: r["value"]
                for r in conn.execute(
                    "SELECT metric_name, value FROM player_metrics WHERE player_id = ?",
                    (prow["id"],),
                )
            }
            p["build_events"] = [
                dict(r) for r in conn.execute(
                    "SELECT game_time_seconds, supply, event_type, name "
                    "FROM build_events WHERE player_id = ? "
                    "AND game_time_seconds > 0 AND game_time_seconds <= 300 "
                    "ORDER BY game_time_seconds",
                    (prow["id"],),
                )
            ]
            players.append(p)

        vocab = tags_vocab.list_all(conn)

    system, user = build_prompt(match, players, vocab)
    raw = call_llm(system, user, model, api_key)
    try:
        parsed = MatchTaggingResponse(**raw)
    except ValidationError as e:
        raise LLMError(f"LLM response failed schema validation: {e}; raw: {raw}") from e

    valid_slugs = {t["slug"] for t in vocab}
    pid_by_index = {p["player_index"]: p["id"] for p in players}

    written = 0
    skipped = 0

    with get_conn() as conn:
        if retag:
            # Clear existing LLM tags for this match's players, then rewrite.
            conn.execute(
                """DELETE FROM player_tags WHERE source = 'llm' AND player_id IN
                   (SELECT id FROM players WHERE match_id = ?)""",
                (match_id,),
            )
            conn.execute("DELETE FROM tagging_runs WHERE match_id = ?", (match_id,))

        for pt in parsed.players:
            player_id = pid_by_index.get(pt.player_index)
            if not player_id:
                continue
            for a in pt.tags:
                if a.tag_slug not in valid_slugs:
                    skipped += 1
                    continue
                conn.execute(
                    """INSERT INTO player_tags
                       (player_id, tag_slug, source, confidence, reasoning, model)
                       VALUES (?, ?, 'llm', ?, ?, ?)
                       ON CONFLICT(player_id, tag_slug, source) DO UPDATE SET
                         confidence = excluded.confidence,
                         reasoning = excluded.reasoning,
                         model = excluded.model""",
                    (player_id, a.tag_slug, a.confidence, a.reasoning, model),
                )
                written += 1

        conn.execute(
            """INSERT INTO tagging_runs (match_id, model, prompt_version, match_summary, raw_response)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(match_id) DO UPDATE SET
                 model = excluded.model,
                 prompt_version = excluded.prompt_version,
                 match_summary = excluded.match_summary,
                 raw_response = excluded.raw_response""",
            (match_id, model, PROMPT_VERSION, parsed.match_summary, json.dumps(raw)),
        )

    return {
        "status": "tagged",
        "match_id": match_id,
        "model": model,
        "tags_written": written,
        "tags_skipped_invalid_slug": skipped,
        "summary": parsed.match_summary,
    }


def tag_untagged(limit: int | None = None) -> dict[str, Any]:
    """Tag all matches that have no tagging_runs row yet."""
    with get_conn() as conn:
        rows = list(conn.execute(
            "SELECT m.id FROM matches m "
            "LEFT JOIN tagging_runs r ON r.match_id = m.id "
            "WHERE r.match_id IS NULL ORDER BY m.played_at DESC"
        ))
    ids = [r["id"] for r in rows]
    if limit:
        ids = ids[:limit]

    tagged = 0
    errors: list[dict[str, Any]] = []
    for mid in ids:
        try:
            tag_match(mid, retag=False)
            tagged += 1
        except Exception as e:
            log.exception("Tagging failed for match %s", mid)
            errors.append({"match_id": mid, "error": str(e)})
    return {"candidates": len(ids), "tagged": tagged, "errors": errors}


# --- Manual tag CRUD on a player ---

def add_manual_tag(player_id: int, tag_slug: str) -> dict:
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM tags WHERE slug = ?", (tag_slug,)).fetchone():
            raise LLMError(f"Unknown tag '{tag_slug}'")
        conn.execute(
            """INSERT OR IGNORE INTO player_tags (player_id, tag_slug, source)
               VALUES (?, ?, 'manual')""",
            (player_id, tag_slug),
        )
    return {"player_id": player_id, "tag_slug": tag_slug, "source": "manual"}


def remove_player_tag(player_id: int, tag_slug: str, source: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM player_tags WHERE player_id = ? AND tag_slug = ? AND source = ?",
            (player_id, tag_slug, source),
        )
        return cur.rowcount > 0


def test_connection() -> dict[str, Any]:
    """Send a tiny 'hello' to verify the API key + model combo works."""
    settings = app_settings.get_all()
    api_key = settings.get("openrouter_api_key", "")
    model = settings.get("tagging_model", "anthropic/claude-haiku-4.5")
    try:
        from litellm import completion
        os.environ["OPENROUTER_API_KEY"] = api_key
        or_model = model if model.startswith("openrouter/") else f"openrouter/{model}"
        resp = completion(
            model=or_model,
            messages=[{"role": "user", "content": "Respond with the single word: OK"}],
            max_tokens=10,
            temperature=0.0,
        )
        content = (resp["choices"][0]["message"]["content"] or "").strip()
        return {"ok": True, "model": model, "response": content[:50]}
    except Exception as e:
        return {"ok": False, "model": model, "error": f"{type(e).__name__}: {e}"}
