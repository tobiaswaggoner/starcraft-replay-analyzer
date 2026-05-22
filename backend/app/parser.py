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
    team: int | None = None
    timeseries: list[dict] = field(default_factory=list)
    build_events: list[dict] = field(default_factory=list)
    apm_minutes: list[dict] = field(default_factory=list)


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


def derive_mode(player_team_human: list[tuple[int | None, bool]]) -> str:
    """Classify a match as 'PvP' / 'PvAI' / 'AI' from (team, is_human) tuples.

    PvP requires that humans are spread across two or more distinct teams.
    A single human team (with humans plus optional AI on other teams) is
    PvAI/coop, regardless of how many humans there are.
    """
    humans = [(t, h) for (t, h) in player_team_human if h]
    if not humans:
        return "AI"
    if len(humans) == 1:
        return "PvAI"
    teams = {t for (t, _) in humans if t is not None}
    if len(teams) >= 2:
        return "PvP"
    if len(teams) == 1:
        return "PvAI"
    return "PvP"  # no team info — conservative legacy default


def derive_game_format(player_team_human: list[tuple[int | None, bool]]) -> str | None:
    """Compute '1v1' / '2v2' / '1v7' from per-player (team, is_human) tuples.

    Logic:
    - Group players by team (drop players with missing team info).
    - If only one team contains humans (coop / PvAI / single-player), collapse
      all non-human-team players into a single opposition bucket → '{n}v{rest}'.
      This avoids 1v7 showing up as '1v1v1v1v1v1v1v1' just because sc2reader
      puts each AI on its own internal team.
    - If 2+ teams contain humans (real PvP), use the per-team sizes joined
      with 'v' so a 2v2 ladder match shows as '2v2'.
    """
    if not player_team_human:
        return None
    by_team: dict[int, dict[str, int]] = {}
    for team, is_human in player_team_human:
        if team is None:
            continue
        b = by_team.setdefault(team, {"humans": 0, "ai": 0})
        if is_human:
            b["humans"] += 1
        else:
            b["ai"] += 1
    if not by_team:
        return None

    human_teams = [t for t, c in by_team.items() if c["humans"] > 0]
    if len(human_teams) <= 1:
        # Collapse the opposition.
        if human_teams:
            ht = human_teams[0]
            humans = by_team[ht]["humans"]
            opposition = sum(c["humans"] + c["ai"] for t, c in by_team.items() if t != ht)
            return f"{humans}v{opposition}"
        # No humans at all — symmetric AI count.
        total_ai = sum(c["ai"] for c in by_team.values())
        return f"{total_ai}v{total_ai}" if total_ai else None

    # Multiple human teams: real PvP, show team sizes directly.
    sizes = sorted(c["humans"] + c["ai"] for c in by_team.values())
    return "v".join(str(s) for s in sizes)


# Classes in sc2reader's Player.events that are NOT meaningful player actions
# for APM purposes. Camera moves and the synthetic CommandManagerStateEvent
# are by far the biggest inflaters versus what SC2's in-game display shows.
_NON_ACTION_EVENT_CLASSES = {
    "CameraEvent",
    "CommandManagerStateEvent",
    "ChatEvent",
    "ProgressEvent",
    "UserOptionsEvent",
    "DialogControlEvent",
    "PlayerLeaveEvent",
}


def _is_action_event(ev) -> bool:
    return ev.__class__.__name__ not in _NON_ACTION_EVENT_CLASSES


def compute_apm_minutes(player, duration_seconds: int) -> list[dict]:
    """Per-minute APM bucket list. Each row: {'minute': i, 'apm': count}."""
    if duration_seconds <= 0:
        return []
    buckets: dict[int, int] = {}
    for ev in getattr(player, "events", []) or []:
        if not _is_action_event(ev):
            continue
        minute = int(getattr(ev, "second", 0) // 60)
        buckets[minute] = buckets.get(minute, 0) + 1
    total_minutes = (duration_seconds + 59) // 60
    return [{"minute": m, "apm": float(buckets.get(m, 0))} for m in range(total_minutes)]


def compute_apm_total(player, duration_seconds: int) -> float | None:
    """Overall APM: action events / minutes."""
    if duration_seconds <= 0:
        return None
    n = sum(1 for ev in getattr(player, "events", []) or [] if _is_action_event(ev))
    if n == 0:
        return None
    return n / (duration_seconds / 60.0)


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
        # We always derive APM ourselves from filtered action events so that
        # the value matches SC2's in-game display reasonably (excluding camera
        # moves, synthetic state events, chat, etc.). sc2reader upstream no
        # longer exposes avg_apm, so we'd have to compute anyway.
        apm = compute_apm_total(p, duration_seconds)

        is_human = bool(_safe(p, "is_human", default=True))
        # Fallback: sc2reader names AI players "A.I. 1 (Very Hard)" etc.
        name = getattr(p, "name", "Unknown") or "Unknown"
        if name.startswith("A.I."):
            is_human = False

        # Capture team membership for game_format derivation + mode classification.
        team_raw = _safe(p, "team_id", "team", default=None)
        team_int: int | None = None
        if team_raw is not None:
            try:
                team_int = int(team_raw)
                teams_seen[team_int] = teams_seen.get(team_int, 0) + 1
            except (TypeError, ValueError):
                team_int = None

        pp = ParsedPlayer(
            player_index=getattr(p, "pid", 0) or 0,
            toon_handle=toon_handle,
            name=name,
            race=race,
            result=result,
            mmr=None,
            apm=apm,
            is_human=is_human,
            team=team_int,
            apm_minutes=compute_apm_minutes(p, duration_seconds),
        )
        parsed_players.append(pp)
        pid_to_player[pp.player_index] = pp

    game_format = derive_game_format([(pp.team, pp.is_human) for pp in parsed_players])
    if game_format is None and parsed_players:
        # Last-ditch fallback when no team info exists at all.
        humans = sum(1 for x in parsed_players if x.is_human)
        ai = len(parsed_players) - humans
        if humans >= 1 and ai >= 1:
            game_format = f"{humans}v{ai}"

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

    # Stamp supply + worker count onto build_events by walking through
    # timeseries (sorted). For each event we take the latest sample at or
    # before its timestamp.
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
            ev["workers"] = ts_sorted[ts_idx].get("workers")

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
