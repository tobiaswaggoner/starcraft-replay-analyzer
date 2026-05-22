"""Parse a single .SC2Replay into normalized dicts ready for DB insert.

Uses sc2reader. We are intentionally defensive about attribute names because
sc2reader exposes raw fields whose names sometimes shift across builds.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sc2reader

log = logging.getLogger(__name__)


def _safe(obj: Any, *names: str, default: Any = None) -> Any:
    for n in names:
        v = getattr(obj, n, None)
        if v is not None:
            return v
    return default


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ParsedPlayer:
    player_index: int
    toon_handle: str | None
    name: str
    race: str
    result: str | None
    mmr: int | None
    apm: float | None
    is_human: bool = True
    timeseries: list[dict] = field(default_factory=list)
    build_events: list[dict] = field(default_factory=list)


@dataclass
class ParsedReplay:
    file_hash: str
    file_path: str
    filename: str
    played_at: str  # ISO 8601
    duration_seconds: int
    map_name: str
    game_version: str | None
    game_type: str | None
    matchup: str | None
    region: str | None
    players: list[ParsedPlayer]
    game_format: str | None = None  # '1v1', '2v2', '1v7', etc.


_RACE_MAP = {"T": "Terran", "Z": "Zerg", "P": "Protoss", "R": "Random"}


def _normalize_race(r: str | None) -> str:
    if not r:
        return "Unknown"
    if r in _RACE_MAP:
        return _RACE_MAP[r]
    return r.capitalize()


def _matchup(players: list[ParsedPlayer]) -> str | None:
    if len(players) != 2:
        return None
    a, b = sorted(p.race[0] for p in players)
    return f"{a}v{b}"


def parse_replay(path: Path) -> ParsedReplay:
    replay = sc2reader.load_replay(str(path), load_level=4)

    played_at = _safe(replay, "start_time", "end_time")
    played_at_iso = played_at.isoformat() if played_at else ""

    duration_seconds = int(_safe(replay, "game_length", "length", default=0).seconds) if _safe(replay, "game_length", "length") else 0

    parsed_players: list[ParsedPlayer] = []
    pid_to_player: dict[int, ParsedPlayer] = {}

    teams_seen: dict[int, int] = {}
    for p in getattr(replay, "players", []) or []:
        race = _normalize_race(_safe(p, "play_race", "pick_race"))
        result = _safe(p, "result")
        toon_handle = _safe(p, "toon_handle")
        apm = _safe(p, "avg_apm", "apm")
        try:
            apm = float(apm) if apm is not None else None
        except (TypeError, ValueError):
            apm = None
        # The sc2reader upstream branch doesn't expose avg_apm; compute it
        # ourselves from the player's event count / game duration in minutes.
        if apm is None:
            events_count = len(getattr(p, "events", []) or [])
            if events_count > 0 and duration_seconds > 0:
                apm = events_count / (duration_seconds / 60.0)

        is_human = bool(_safe(p, "is_human", default=True))
        # Fallback: sc2reader names AI players "A.I. 1 (Very Hard)" etc.
        name = getattr(p, "name", "Unknown") or "Unknown"
        if name.startswith("A.I."):
            is_human = False

        # Capture team membership for game_format derivation.
        team_id = _safe(p, "team_id", "team", default=None)
        if team_id is not None:
            teams_seen[int(team_id)] = teams_seen.get(int(team_id), 0) + 1

        pp = ParsedPlayer(
            player_index=getattr(p, "pid", 0) or 0,
            toon_handle=toon_handle,
            name=name,
            race=race,
            result=result,
            mmr=None,
            apm=apm,
            is_human=is_human,
        )
        parsed_players.append(pp)
        pid_to_player[pp.player_index] = pp

    # game_format: sort team sizes ascending → "1v7", "2v2", "1v1".
    if teams_seen:
        sizes = sorted(teams_seen.values())
        game_format = "v".join(str(s) for s in sizes)
    elif parsed_players:
        humans = sum(1 for x in parsed_players if x.is_human)
        ai = len(parsed_players) - humans
        if ai == 0:
            game_format = f"{humans}v{humans}"
        else:
            game_format = f"{humans}v{ai}"
    else:
        game_format = None

    for ev in getattr(replay, "tracker_events", []) or []:
        cls_name = ev.__class__.__name__
        if cls_name == "PlayerStatsEvent":
            pp = pid_to_player.get(getattr(ev, "pid", -1))
            if not pp:
                continue
            pp.timeseries.append({
                "game_time_seconds": float(getattr(ev, "second", 0.0)),
                "workers": _safe(ev, "workers_active_count"),
                "supply_used": _safe(ev, "food_used"),
                "supply_cap": _safe(ev, "food_made"),
                "minerals_collected": _safe(ev, "minerals_collection_rate"),
                "gas_collected": _safe(ev, "vespene_collection_rate"),
                "army_value": _safe(ev, "minerals_used_active_forces", default=0) + _safe(ev, "vespene_used_active_forces", default=0),
            })
        elif cls_name in ("UnitBornEvent", "UnitInitEvent"):
            pid = _safe(ev, "control_pid", "unit_controller_pid", default=0)
            pp = pid_to_player.get(pid)
            if not pp:
                continue
            unit = getattr(ev, "unit", None)
            unit_name = getattr(unit, "name", None) if unit else None
            if not unit_name:
                unit_name = _safe(ev, "unit_type_name") or "Unknown"
            # Skip larvae, eggs, beacons, broodlings, larva spawn artifacts
            if unit_name in {"Larva", "Egg", "Broodling", "BroodlingEscort", "InvisibleTargetDummy"}:
                continue
            pp.build_events.append({
                "game_time_seconds": float(getattr(ev, "second", 0.0)),
                "supply": None,
                "event_type": "born" if cls_name == "UnitBornEvent" else "init",
                "name": unit_name,
            })
        elif cls_name == "UpgradeCompleteEvent":
            pp = pid_to_player.get(getattr(ev, "pid", -1))
            if not pp:
                continue
            upgrade_name = _safe(ev, "upgrade_type_name") or "Unknown"
            if upgrade_name.lower().startswith(("spraysprite", "sprayterran", "spray")):
                continue
            pp.build_events.append({
                "game_time_seconds": float(getattr(ev, "second", 0.0)),
                "supply": None,
                "event_type": "upgrade",
                "name": upgrade_name,
            })

    # Dedupe timeseries by second (sc2reader can emit multiple PlayerStatsEvent
    # at the same second; keep the latest one).
    for pp in parsed_players:
        if not pp.timeseries:
            continue
        by_second: dict[float, dict] = {}
        for row in pp.timeseries:
            by_second[row["game_time_seconds"]] = row
        pp.timeseries = list(by_second.values())

    # Stamp supply onto build_events by walking through timeseries (sorted)
    for pp in parsed_players:
        if not pp.timeseries:
            continue
        ts_sorted = sorted(pp.timeseries, key=lambda r: r["game_time_seconds"])
        ts_idx = 0
        pp.build_events.sort(key=lambda r: r["game_time_seconds"])
        for ev in pp.build_events:
            while ts_idx + 1 < len(ts_sorted) and ts_sorted[ts_idx + 1]["game_time_seconds"] <= ev["game_time_seconds"]:
                ts_idx += 1
            ev["supply"] = ts_sorted[ts_idx].get("supply_used")

    fh = file_hash(path)

    return ParsedReplay(
        file_hash=fh,
        file_path=str(path.resolve()),
        filename=path.name,
        played_at=played_at_iso,
        duration_seconds=duration_seconds,
        map_name=_safe(replay, "map_name", default="Unknown"),
        game_version=_safe(replay, "release_string", "build"),
        game_type=_safe(replay, "real_type", "game_type"),
        matchup=_matchup(parsed_players),
        region=_safe(replay, "region"),
        players=parsed_players,
        game_format=game_format,
    )
