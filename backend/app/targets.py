"""Training targets: persistent rules ('workers @ 5min ≥ 60') evaluated per match.

Targets live in the DB and are CRUD-managed via the UI. Evaluation is on-the-fly
from existing per-player metrics — no separate evaluations table to keep in sync.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from pydantic import BaseModel, Field, field_validator

OPERATORS = (">=", "<=", "==")


class TargetIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    metric_name: str
    operator: str
    threshold: float
    race: str | None = None
    matchup: str | None = None
    mode: str | None = None
    enabled: bool = True

    @field_validator("operator")
    @classmethod
    def _op_valid(cls, v: str) -> str:
        if v not in OPERATORS:
            raise ValueError(f"operator must be one of {OPERATORS}")
        return v


class Target(TargetIn):
    id: int
    created_at: str


def list_targets(conn: sqlite3.Connection) -> list[dict]:
    return [_row_to_target(r) for r in conn.execute(
        "SELECT * FROM training_targets ORDER BY created_at DESC, id DESC"
    )]


def get_target(conn: sqlite3.Connection, target_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM training_targets WHERE id = ?", (target_id,)).fetchone()
    return _row_to_target(r) if r else None


def create_target(conn: sqlite3.Connection, t: TargetIn) -> dict:
    cur = conn.execute(
        """INSERT INTO training_targets (name, metric_name, operator, threshold,
            race, matchup, mode, enabled)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (t.name, t.metric_name, t.operator, t.threshold,
         t.race, t.matchup, t.mode, 1 if t.enabled else 0),
    )
    return get_target(conn, cur.lastrowid)  # type: ignore[return-value]


def update_target(conn: sqlite3.Connection, target_id: int, t: TargetIn) -> dict | None:
    conn.execute(
        """UPDATE training_targets SET name=?, metric_name=?, operator=?, threshold=?,
            race=?, matchup=?, mode=?, enabled=? WHERE id=?""",
        (t.name, t.metric_name, t.operator, t.threshold,
         t.race, t.matchup, t.mode, 1 if t.enabled else 0, target_id),
    )
    return get_target(conn, target_id)


def delete_target(conn: sqlite3.Connection, target_id: int) -> bool:
    cur = conn.execute("DELETE FROM training_targets WHERE id = ?", (target_id,))
    return cur.rowcount > 0


def _row_to_target(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "metric_name": row["metric_name"],
        "operator": row["operator"],
        "threshold": row["threshold"],
        "race": row["race"],
        "matchup": row["matchup"],
        "mode": row["mode"],
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
    }


def applies_to(target: dict, match: dict, my_player: dict | None) -> bool:
    """Whether a target should be evaluated for this match given its scope filters."""
    if not target["enabled"]:
        return False
    if target["mode"] and target["mode"] != match.get("mode"):
        return False
    if target["matchup"] and target["matchup"] != match.get("matchup"):
        return False
    if target["race"]:
        if not my_player or my_player.get("race") != target["race"]:
            return False
    return True


def evaluate(target: dict, my_player: dict | None) -> dict[str, Any]:
    """Returns {target_id, value, pass, delta} for a target against a player's metrics."""
    out: dict[str, Any] = {"target_id": target["id"], "value": None, "pass": None, "delta": None}
    if not my_player:
        return out
    val = my_player.get("metrics", {}).get(target["metric_name"])
    if val is None:
        return out
    th = target["threshold"]
    op = target["operator"]
    if op == ">=":
        passed = val >= th
    elif op == "<=":
        passed = val <= th
    else:
        passed = abs(val - th) < 1e-9
    out["value"] = val
    out["pass"] = passed
    out["delta"] = val - th
    return out
