"""Metric definitions.

Each metric is a function from ParsedPlayer (+ ParsedReplay context) to a float
value. New metrics: write a function, decorate with @metric. They are computed
at ingest time and persisted in player_metrics. Reingest after adding metrics.
"""

from __future__ import annotations

from typing import Callable

from .parser import ParsedPlayer, ParsedReplay

MetricFn = Callable[[ParsedPlayer, ParsedReplay], float | None]
REGISTRY: dict[str, MetricFn] = {}


def metric(name: str):
    def deco(fn: MetricFn) -> MetricFn:
        REGISTRY[name] = fn
        return fn
    return deco


def _sample_at(player: ParsedPlayer, seconds: float, field: str) -> float | None:
    if not player.timeseries:
        return None
    chosen = None
    for row in sorted(player.timeseries, key=lambda r: r["game_time_seconds"]):
        if row["game_time_seconds"] <= seconds:
            chosen = row
        else:
            break
    if chosen is None:
        return None
    val = chosen.get(field)
    return float(val) if val is not None else None


@metric("apm")
def m_apm(p: ParsedPlayer, r: ParsedReplay) -> float | None:
    return p.apm


@metric("workers_at_4min")
def m_workers_at_4min(p: ParsedPlayer, r: ParsedReplay) -> float | None:
    return _sample_at(p, 240.0, "workers")


@metric("workers_at_8min")
def m_workers_at_8min(p: ParsedPlayer, r: ParsedReplay) -> float | None:
    return _sample_at(p, 480.0, "workers")


@metric("workers_peak")
def m_workers_peak(p: ParsedPlayer, r: ParsedReplay) -> float | None:
    if not p.timeseries:
        return None
    return float(max((row.get("workers") or 0) for row in p.timeseries))


@metric("supply_peak")
def m_supply_peak(p: ParsedPlayer, r: ParsedReplay) -> float | None:
    if not p.timeseries:
        return None
    return float(max((row.get("supply_used") or 0) for row in p.timeseries))


@metric("supply_blocked_seconds")
def m_supply_blocked(p: ParsedPlayer, r: ParsedReplay) -> float | None:
    """Approximate: sum of sample-intervals where supply_used == supply_cap and < 200."""
    if not p.timeseries:
        return None
    rows = sorted(p.timeseries, key=lambda r_: r_["game_time_seconds"])
    total = 0.0
    for i in range(len(rows) - 1):
        used = rows[i].get("supply_used") or 0
        cap = rows[i].get("supply_cap") or 0
        if used >= cap and cap < 200 and cap > 0:
            total += rows[i + 1]["game_time_seconds"] - rows[i]["game_time_seconds"]
    return total


@metric("time_to_max_supply")
def m_time_to_max(p: ParsedPlayer, r: ParsedReplay) -> float | None:
    """First moment supply_cap reaches 200. None if never maxed."""
    if not p.timeseries:
        return None
    for row in sorted(p.timeseries, key=lambda r_: r_["game_time_seconds"]):
        if (row.get("supply_cap") or 0) >= 200:
            return float(row["game_time_seconds"])
    return None


def compute_all(p: ParsedPlayer, r: ParsedReplay) -> dict[str, float | None]:
    return {name: fn(p, r) for name, fn in REGISTRY.items()}
