"""Changes that could take the warm, still water out of a building, what they cost, and the best set
for a budget, found by simulating every allowed combination (so it can't miss the best one).

Costs are rough Australian prices for planning, not quotes.
"""

from __future__ import annotations

import copy
import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from .model import Building, PlanError, load
from .sim import Settings, simulate

LAG_PER_M = 15.0  # closed-cell lagging fitted in the roof space, $/m
REROUTE_PER_M = 70.0  # a plumber moving pipe out of the roof space, $/m
POU_TMV = 600.0  # a tempering valve fitted at a bathroom, $ each
FLUSH_VALVE = 700.0  # an automatic timed flushing valve, $ per room
CAP_ROOM = 450.0  # removing and capping a room's outlets back to the main
HOTTER = 45.0  # a year of extra heater losses at +5 °C, roughly
RARE_DAYS = 1  # rooms whose outlets are used on this many days a week or fewer are "rarely used"


@dataclass(frozen=True)
class Fix:
    id: str
    title: str
    detail: str
    cost: float
    group: str  # fixes in the same group are alternatives: at most one is chosen
    habit: bool = False


def _length(p: dict[str, Any]) -> float:
    pts = p["points"]
    return float(p.get("length") or sum(math.dist(a, b) for a, b in pairwise(pts)))


def _room_of(b: Building, at: tuple[float, float, float]) -> str:
    for r in b.rooms:
        x0, z0, x1, z1 = r.box
        if min(x0, x1) <= at[0] <= max(x0, x1) and min(z0, z1) <= at[2] <= max(z0, z1):
            return r.name
    return "the building"


def _short(room: str) -> str:
    """A room's name for use mid-sentence: "the guest bathroom", "Room 4"."""
    base = room.split(" (", maxsplit=1)[0]
    return base if base[:1].isupper() and any(c.isdigit() for c in base) else base.lower()


def _the(names: str) -> str:
    return names if names[:1].isupper() else "the " + names


def rare_rooms(b: Building) -> dict[str, list[str]]:
    """Rooms whose outlets are all used on few days of the week, with those outlets."""
    rooms: dict[str, list[str]] = {}
    for oid, o in b.outlets.items():
        rooms.setdefault(_room_of(b, o.at), []).append(oid)
    out = {}
    for room, oids in rooms.items():
        days: set[int] = set()
        for oid in oids:
            for u in b.outlets[oid].uses:
                days.update(u.days)
        if len(days) <= RARE_DAYS:
            out[room] = sorted(oids)
    return out


def candidates(data: dict[str, Any]) -> list[Fix]:
    b = load(data)
    raw = {p["id"]: p for p in data["pipes"]}
    fixes: list[Fix] = []
    temp_roof = [pid for pid, p in b.pipes.items() if p.zone == "roof" and p.kind in ("hot", "tempered") and p.insulation == 0]
    cold_roof = [pid for pid, p in b.pipes.items() if p.zone == "roof" and p.kind == "cold"]
    cold_bare = [pid for pid in cold_roof if b.pipes[pid].insulation == 0]
    hot_roof = [pid for pid, p in b.pipes.items() if p.zone == "roof" and p.kind in ("hot", "tempered")]
    if temp_roof:
        m = sum(_length(raw[p]) for p in temp_roof)
        fixes.append(
            Fix(
                "lag-hot",
                "Lag the hot and tempered pipes in the roof",
                f"{m:.0f} m of 13 mm closed-cell lagging",
                round(m * LAG_PER_M),
                "hot-roof",
            )
        )
    if hot_roof:
        m = sum(_length(raw[p]) for p in hot_roof)
        fixes.append(
            Fix(
                "move-hot",
                "Move the hot and tempered pipes out of the roof",
                f"{m:.0f} m re-run under the floor and in the walls",
                round(m * REROUTE_PER_M),
                "hot-roof",
            )
        )
    if cold_bare:
        m = sum(_length(raw[p]) for p in cold_bare)
        fixes.append(
            Fix(
                "lag-cold",
                "Lag the cold pipes in the roof",
                f"{m:.0f} m of 13 mm closed-cell lagging",
                round(m * LAG_PER_M),
                "cold-roof",
            )
        )
    if cold_roof:
        m = sum(_length(raw[p]) for p in cold_roof)
        fixes.append(
            Fix(
                "move-cold",
                "Move the cold pipes out of the roof",
                f"{m:.0f} m re-run under the floor and in the walls",
                round(m * REROUTE_PER_M),
                "cold-roof",
            )
        )
    for t in b.tmvs.values():
        served = [oid for oid, o in b.outlets.items() if o.hot and b.pipes[o.hot].kind == "tempered" and t.hot in b.path(o.hot)]
        rooms = sorted({_room_of(b, b.outlets[o].at) for o in served})
        if len(rooms) > 1:
            fixes.append(
                Fix(
                    f"pou-{t.id}",
                    "Temper at each bathroom instead",
                    f"{len(rooms)} tempering valves, one per room, and 60 °C water in the pipes up to them",
                    round(len(rooms) * POU_TMV),
                    f"pou-{t.id}",
                )
            )
    if b.setpoint < 65:
        fixes.append(
            Fix(
                "hotter",
                "Set the water heater to 65 °C",
                "a year of extra heat loss; the tempering valves keep showers at a safe temperature",
                HOTTER,
                "hotter",
            )
        )
    rare = rare_rooms(b)
    if rare:
        n = len(rare)
        names = " and ".join(_short(r) for r in sorted(rare)) if n <= 2 else f"{n} rarely used rooms"
        fixes.append(
            Fix(
                "habit",
                f"Run the taps in {_the(names)} twice a week",
                "two minutes each, hot and cold, on Wednesdays and Saturdays",
                0,
                "rare",
                habit=True,
            )
        )
        fixes.append(
            Fix(
                "flush",
                f"Automatic flushing valve{'s' if n > 1 else ''} in {_the(names)}",
                "runs each outlet two minutes every night",
                FLUSH_VALVE * n,
                "rare",
            )
        )
        if data.get("cap_rare", True) is not False:
            fixes.append(
                Fix(
                    "cap", f"Remove the outlets in {_the(names)} and cap the pipes", "if they aren't needed", CAP_ROOM * n, "rare"
                )
            )
    return fixes


def apply(data: dict[str, Any], chosen: list[str]) -> tuple[dict[str, Any], dict[str, list[tuple[float, float]]]]:
    """Returns the changed plan and any extra flushing uses, for the chosen fix ids."""
    d = copy.deepcopy(data)
    b = load(data)
    extra: dict[str, list[tuple[float, float]]] = {}
    rare = sorted(rare_rooms(b).items())
    pipes = {p["id"]: p for p in d["pipes"]}
    for fid in chosen:
        if fid == "lag-hot":
            for pid, p in b.pipes.items():
                if p.zone == "roof" and p.kind in ("hot", "tempered") and p.insulation == 0:
                    pipes[pid]["insulation"] = 13
        elif fid == "lag-cold":
            for pid, p in b.pipes.items():
                if p.zone == "roof" and p.kind == "cold":
                    pipes[pid]["insulation"] = max(13, pipes[pid].get("insulation", 0))
        elif fid == "move-cold":
            for pid, p in b.pipes.items():
                if p.zone == "roof" and p.kind == "cold":
                    pipes[pid]["zone"] = "wall"
        elif fid == "hotter":
            d["setpoint"] = 65
        elif fid.startswith("pou-"):
            _point_of_use(d, b, fid[4:])
            pipes = {p["id"]: p for p in d["pipes"]}
        elif fid == "move-hot":
            for pid, p in b.pipes.items():
                if p.zone == "roof" and p.kind in ("hot", "tempered"):
                    pipes[pid]["zone"] = "wall"
        elif fid in ("habit", "flush", "cap"):
            room_oids = [oid for _, oids in rare for oid in oids]
            if fid == "cap":
                d["outlets"] = [o for o in d["outlets"] if o["id"] not in room_oids]
                _prune(d)
                pipes = {p["id"]: p for p in d["pipes"]}
            elif fid == "flush":
                for oid in room_oids:
                    extra[oid] = [(3.0, 2.0)]
            else:
                for o in d["outlets"]:
                    if o["id"] in room_oids:
                        o["uses"] = [*o["uses"], {"at": 18.0, "minutes": 2, "days": [2, 5], "flush": True}]
        else:
            raise ValueError(f"unknown fix {fid}")
    return d, extra


def _point_of_use(d: dict[str, Any], b: Building, tmv_id: str) -> None:
    """Every pipe the central valve fed now carries hot water; each room gets its own valve."""
    t = b.tmvs[tmv_id]
    by_room: dict[str, list[str]] = {}
    for oid, o in b.outlets.items():
        if o.hot and b.pipes[o.hot].kind == "tempered" and t.hot in b.path(o.hot):
            by_room.setdefault(_room_of(b, o.at), []).append(oid)
    for p in d["pipes"]:
        if p["from"] == f"tmv:{tmv_id}":
            p["from"] = f"pipe:{t.hot}"
    d["tmvs"] = [x for x in d["tmvs"] if x["id"] != tmv_id]
    for k, (_room, oids) in enumerate(sorted(by_room.items())):
        first = b.outlets[oids[0]]
        if not (first.hot and first.cold):
            raise PlanError(f"{first.name} needs both a hot and a cold pipe to get its own tempering valve")
        hp, cp = b.pipes[first.hot].points[-1], b.pipes[first.cold].points[-1]
        at = [round((hp[0] + cp[0]) / 2, 3), 0.4, round((hp[2] + cp[2]) / 2, 3)]
        vid = f"{tmv_id}-{k}"
        d["pipes"].append(
            {"id": f"{vid}-h", "from": f"pipe:{first.hot}", "zone": "wall", "points": [list(hp), at], "length": 0.4}
        )
        d["pipes"].append(
            {"id": f"{vid}-c", "from": f"pipe:{first.cold}", "zone": "wall", "points": [list(cp), at], "length": 0.4}
        )
        d["tmvs"].append({"id": vid, "hot": f"{vid}-h", "cold": f"{vid}-c", "set": t.set, "at": at})
        for oid in oids:
            o = next(x for x in d["outlets"] if x["id"] == oid)
            out_at = list(b.outlets[oid].at)
            pid = f"{vid}-{oid}"
            d["pipes"].append({"id": pid, "from": f"tmv:{vid}", "zone": "wall", "points": [at, out_at], "length": 0.8})
            o["hot"] = pid
    _prune(d)


def _prune(d: dict[str, Any]) -> None:
    """Removes pipes that no longer lead to any outlet or valve (capped back to the main)."""
    while True:
        used = {o["hot"] for o in d["outlets"]} | {o["cold"] for o in d["outlets"]}
        used |= {t["hot"] for t in d["tmvs"]} | {t["cold"] for t in d["tmvs"]}
        fed = {p["from"][5:] for p in d["pipes"] if p["from"].startswith("pipe:")}
        keep = [p for p in d["pipes"] if p["id"] in used or p["id"] in fed]
        if len(keep) == len(d["pipes"]):
            return
        d["pipes"] = keep


def combinations(fixes: list[Fix]) -> list[tuple[str, ...]]:
    """Every set of fixes with at most one from each group."""
    groups: dict[str, list[str]] = {}
    for f in fixes:
        groups.setdefault(f.group, []).append(f.id)
    options = [[None, *ids] for ids in groups.values()]
    return [tuple(x for x in combo if x) for combo in itertools.product(*options)]


def plan(data: dict[str, Any], settings: Settings, progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    """Simulates every allowed combination; returns each one's cost and risk, and the frontier."""
    fixes = candidates(data)
    costs = {f.id: f.cost for f in fixes}
    combos = combinations(fixes)
    quiet = Settings(**{**settings.__dict__, "record_day": -1})
    rows = []
    for i, combo in enumerate(combos):
        d, extra = apply(data, list(combo))
        r = simulate(load(d), quiet, extra)
        rows.append(
            {
                "fixes": list(combo),
                "cost": sum(costs[c] for c in combo),
                "score": r["score"],
                "outlets": {k: v["risky_litres"] for k, v in r["outlets"].items()},
            }
        )
        if progress:
            progress(i + 1, len(combos))
    baseline = next(r for r in rows if not r["fixes"])
    rows.sort(key=lambda r: (r["cost"], r["score"], len(r["fixes"])))
    frontier: list[dict[str, Any]] = []
    best = math.inf
    for r in rows:
        # a point on the frontier must beat every cheaper set by a meaningful margin
        if not frontier or r["score"] < best - max(0.05, 0.005 * best):
            frontier.append(r)
            best = r["score"]
    names = {oid: o.name for oid, o in load(data).outlets.items()}
    return {"fixes": [f.__dict__ for f in fixes], "names": names, "baseline": baseline, "combos": rows, "frontier": frontier}


def best_for(result: dict[str, Any], budget: float) -> dict[str, Any]:
    """The lowest-risk set of fixes within a budget (the cheapest, if several tie)."""
    within = [r for r in result["frontier"] if r["cost"] <= budget + 1e-9]
    best: dict[str, Any] = within[-1]
    return best
