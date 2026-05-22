"""Tag vocabulary: DB is the runtime source of truth; YAML is the seed.

Behavior on backend start:
- If the `tags` table is empty, import all tags from `tags_seed.yaml`.
- Otherwise leave the DB alone.

`reset_to_seed()` re-imports the YAML, refreshing system tags while leaving
any user-created tags untouched.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

_SEED_PATH = Path(__file__).parent / "tags_seed.yaml"

ALLOWED_CATEGORIES = {"strategy", "tech", "build", "tempo", "outcome"}
ALLOWED_RACES = {"Terran", "Zerg", "Protoss"}


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    category: str
    description: str | None = None
    applies_to_races: list[str] | None = None
    color: str | None = None

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str) -> str:
        if v not in ALLOWED_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(ALLOWED_CATEGORIES)}")
        return v

    @field_validator("applies_to_races")
    @classmethod
    def _races(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        for r in v:
            if r not in ALLOWED_RACES:
                raise ValueError(f"race must be one of {sorted(ALLOWED_RACES)}")
        return v


class TagCreate(TagIn):
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")


def seed_if_empty(conn: sqlite3.Connection) -> int:
    """Import YAML seed if `tags` is empty. Returns the count of tags imported."""
    n = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    if n > 0:
        return 0
    return _import_seed(conn, overwrite_system=True)


def reset_seed(conn: sqlite3.Connection) -> int:
    """Re-import seed tags (refresh system tags; user tags untouched)."""
    return _import_seed(conn, overwrite_system=True)


def _import_seed(conn: sqlite3.Connection, overwrite_system: bool) -> int:
    data = yaml.safe_load(_SEED_PATH.read_text(encoding="utf-8"))
    categories = data.get("categories", {})
    tags = data.get("tags", [])
    n = 0
    for t in tags:
        slug = t["slug"]
        cat = t.get("category", "strategy")
        color = t.get("color") or categories.get(cat, {}).get("color") or "#9aa3b6"
        races = t.get("applies_to_races")
        races_json = json.dumps(races) if races else None
        if overwrite_system:
            conn.execute(
                """INSERT INTO tags (slug, name, category, description,
                       applies_to_races, color, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, 'system')
                   ON CONFLICT(slug) DO UPDATE SET
                       name = excluded.name,
                       category = excluded.category,
                       description = excluded.description,
                       applies_to_races = excluded.applies_to_races,
                       color = excluded.color
                   WHERE tags.created_by = 'system'""",
                (slug, t["name"], cat, t.get("description"), races_json, color),
            )
        else:
            conn.execute(
                """INSERT OR IGNORE INTO tags (slug, name, category, description,
                       applies_to_races, color, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, 'system')""",
                (slug, t["name"], cat, t.get("description"), races_json, color),
            )
        n += 1
    return n


def list_all(conn: sqlite3.Connection) -> list[dict]:
    return [_row_to_tag(r) for r in conn.execute(
        "SELECT * FROM tags ORDER BY category, name"
    )]


def get_one(conn: sqlite3.Connection, slug: str) -> dict | None:
    r = conn.execute("SELECT * FROM tags WHERE slug = ?", (slug,)).fetchone()
    return _row_to_tag(r) if r else None


def create(conn: sqlite3.Connection, payload: TagCreate) -> dict:
    races = json.dumps(payload.applies_to_races) if payload.applies_to_races else None
    conn.execute(
        """INSERT INTO tags (slug, name, category, description, applies_to_races, color, created_by)
           VALUES (?, ?, ?, ?, ?, ?, 'user')""",
        (payload.slug, payload.name, payload.category, payload.description,
         races, payload.color or _default_color(payload.category)),
    )
    return get_one(conn, payload.slug)  # type: ignore[return-value]


def update(conn: sqlite3.Connection, slug: str, payload: TagIn) -> dict | None:
    races = json.dumps(payload.applies_to_races) if payload.applies_to_races else None
    conn.execute(
        """UPDATE tags SET name = ?, category = ?, description = ?,
              applies_to_races = ?, color = ? WHERE slug = ?""",
        (payload.name, payload.category, payload.description, races, payload.color, slug),
    )
    return get_one(conn, slug)


def delete(conn: sqlite3.Connection, slug: str) -> bool:
    cur = conn.execute("DELETE FROM tags WHERE slug = ?", (slug,))
    return cur.rowcount > 0


def _row_to_tag(row: sqlite3.Row) -> dict:
    return {
        "slug": row["slug"],
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "applies_to_races": json.loads(row["applies_to_races"]) if row["applies_to_races"] else None,
        "color": row["color"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


_DEFAULT_COLORS = {
    "strategy": "#6ea2ff",
    "tech": "#a3d977",
    "build": "#f1c83b",
    "tempo": "#f78fb3",
    "outcome": "#9aa3b6",
}


def _default_color(category: str) -> str:
    return _DEFAULT_COLORS.get(category, "#9aa3b6")


def applicable_to_race(tag: dict, race: str | None) -> bool:
    races = tag.get("applies_to_races")
    if not races:
        return True
    return race in races
