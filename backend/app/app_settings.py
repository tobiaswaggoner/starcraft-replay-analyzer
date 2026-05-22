"""DB-backed app settings (API key, model choice, auto-tag toggle, etc.).

These complement the .env file: .env stays for things that rarely change and
require a backend restart (REPLAY_DIR, MY_PLAYER_NAMES, DB_PATH, HOST/PORT).
This module is for user-tunable runtime settings.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .db import get_conn

# Default values applied on first read.
DEFAULTS: dict[str, Any] = {
    "openrouter_api_key": "",
    "tagging_model": "anthropic/claude-haiku-4.5",
    "auto_tag_on_ingest": True,
}

# Curated model list. Refresh by re-querying OpenRouter as models evolve.
AVAILABLE_MODELS: list[dict[str, str]] = [
    {"id": "anthropic/claude-haiku-4.5",  "label": "Claude Haiku 4.5",  "tier": "fast"},
    {"id": "anthropic/claude-sonnet-4.6", "label": "Claude Sonnet 4.6", "tier": "balanced"},
    {"id": "anthropic/claude-opus-4.7",   "label": "Claude Opus 4.7",   "tier": "premium"},
    {"id": "openai/gpt-5-mini",           "label": "GPT-5 mini",        "tier": "fast"},
    {"id": "openai/gpt-5.1",              "label": "GPT-5.1",           "tier": "balanced"},
    {"id": "google/gemini-3.5-flash",     "label": "Gemini 3.5 Flash",  "tier": "fast"},
]


def get_all() -> dict[str, Any]:
    out = dict(DEFAULTS)
    with get_conn() as conn:
        for row in conn.execute("SELECT key, value FROM app_settings"):
            try:
                out[row["key"]] = json.loads(row["value"])
            except (TypeError, ValueError):
                out[row["key"]] = row["value"]
    return out


def get(key: str) -> Any:
    return get_all().get(key, DEFAULTS.get(key))


def set_many(updates: dict[str, Any]) -> dict[str, Any]:
    with get_conn() as conn:
        for k, v in updates.items():
            _upsert(conn, k, v)
    return get_all()


def _upsert(conn: sqlite3.Connection, key: str, value: Any) -> None:
    raw = json.dumps(value)
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, raw),
    )


def mask_secret(value: str) -> str:
    """Mask an API key for display ('sk-or-...abcd')."""
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return value[:6] + "…" + value[-4:]


def get_public_view() -> dict[str, Any]:
    """Settings view safe for the UI: api key is masked."""
    s = get_all()
    out = dict(s)
    out["openrouter_api_key_masked"] = mask_secret(s.get("openrouter_api_key", ""))
    out["openrouter_api_key_set"] = bool(s.get("openrouter_api_key"))
    out.pop("openrouter_api_key", None)
    return out
