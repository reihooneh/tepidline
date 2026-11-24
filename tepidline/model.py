"""A building's water pipes, tempering valves and outlets, read from JSON and checked.

Pipes form trees. Each pipe is fed from its upstream end by a source ("hot" from the water heater,
"cold" from the mains, "tmv:<id>" from a tempering valve) or by another pipe ("pipe:<id>"). Outlets
draw from the downstream end of a hot (or tempered) pipe and/or a cold pipe, mixing to the
temperature the person wants. Every field is range-checked: a plan is untrusted input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from .physics import SIZES, PipeThermal, pipe_thermal

ZONES = ("roof", "wall", "underfloor", "outdoor", "indoor")
KINDS = {  # outlet kind: (aerosol weight, typical flow L/min, temperature people use °C)
    "shower": (1.0, 9.0, 40.0),
    "bath": (0.3, 12.0, 41.0),
    "basin": (0.2, 5.0, 38.0),
    "kitchen": (0.2, 7.0, 45.0),
    "laundry": (0.1, 8.0, 35.0),
}
MAX_PIPES = 200
MAX_OUTLETS = 60
MAX_USES = 40


class PlanError(ValueError):
    """A building plan that can't be used, with a message for people."""


@dataclass
class Pipe:
    id: str
    source: str  # "hot", "cold", "tmv:<id>" or "pipe:<id>"
    length: float
    dn: int
    material: str
    insulation: float
    zone: str
    points: list[tuple[float, float, float]]
    kind: str = ""  # hot, cold or tempered: filled in by the checks
    thermal: PipeThermal = field(init=False)

    def __post_init__(self) -> None:
        self.thermal = pipe_thermal(self.material, self.dn, self.insulation)

    @property
    def volume(self) -> float:
        return self.thermal.volume_per_m * self.length


@dataclass
class Tmv:
    id: str
    hot: str
    cold: str
    set: float
    at: tuple[float, float, float]


@dataclass
class Use:
    at: float  # hour of the day
    minutes: float
    days: tuple[int, ...]  # 0 = Monday
    flush: bool = False  # run to waste to freshen the pipes, with nobody breathing the spray


@dataclass
class Outlet:
    id: str
    name: str
    kind: str
    hot: str | None
    cold: str | None
    uses: list[Use]
    flow: float  # L/min
    temp: float  # what people mix to
    at: tuple[float, float, float]

    @property
    def weight(self) -> float:
        return KINDS[self.kind][0]


@dataclass
class Room:
    name: str
    box: tuple[float, float, float, float]  # x0, z0, x1, z1 (metres, plan view)


@dataclass
class Building:
    name: str
    setpoint: float
    pipes: dict[str, Pipe]
    tmvs: dict[str, Tmv]
    outlets: dict[str, Outlet]
    rooms: list[Room]
    heater_at: tuple[float, float, float]
    meter_at: tuple[float, float, float]
    size: tuple[float, float, float]  # footprint x, z and wall height
    children: dict[str, list[str]] = field(default_factory=dict)

    def path(self, pipe_id: str) -> list[str]:
        """Pipes from `pipe_id` up to its source, including through tempering valves (both sides)."""
        out: list[str] = []
        stack = [pipe_id]
        while stack:
            p = stack.pop()
            if p in out:
                continue
            out.append(p)
            src = self.pipes[p].source
            if src.startswith("pipe:"):
                stack.append(src[5:])
            elif src.startswith("tmv:"):
                t = self.tmvs[src[4:]]
                stack += [t.hot, t.cold]
        return out

    def outlet_pipes(self, outlet_id: str) -> set[str]:
        o = self.outlets[outlet_id]
        s: set[str] = set()
        for leaf in (o.hot, o.cold):
            if leaf:
                s.update(self.path(leaf))
        return s


# ---------------------------------------------------------------- reading and checking


def _num(d: dict[str, Any], key: str, lo: float, hi: float, default: float | None = None) -> float:
    v = d.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise PlanError(f"{key} must be a number")
    if not lo <= v <= hi:
        raise PlanError(f"{key} must be between {lo:g} and {hi:g}")
    return float(v)


def _str(d: dict[str, Any], key: str, max_len: int = 40) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not 0 < len(v) <= max_len or any(ord(c) < 32 for c in v):
        raise PlanError(f"{key} must be a short piece of text")
    return v


def _point(v: Any, what: str) -> tuple[float, float, float]:
    if not isinstance(v, list) or len(v) != 3:
        raise PlanError(f"{what} must be [x, y, z] in metres")
    out = []
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or abs(x) > 500:
            raise PlanError(f"{what} must be [x, y, z] in metres")
        out.append(float(x))
    return out[0], out[1], out[2]


def _ident(d: dict[str, Any], key: str) -> str:
    v = _str(d, key, 24)
    if not all(c.isalnum() or c in "-_" for c in v):
        raise PlanError(f"{key} may use only letters, digits, - and _")
    return v


def load(data: Any) -> Building:
    """Builds and checks a Building from parsed JSON."""
    if not isinstance(data, dict):
        raise PlanError("the plan must be a JSON object")
    name = _str(data, "name", 60)
    setpoint = _num(data, "setpoint", 45, 75, 60)
    raw_pipes = data.get("pipes")
    raw_outlets = data.get("outlets")
    if not isinstance(raw_pipes, list) or not 0 < len(raw_pipes) <= MAX_PIPES:
        raise PlanError(f"pipes must be a list of 1 to {MAX_PIPES}")
    if not isinstance(raw_outlets, list) or not 0 < len(raw_outlets) <= MAX_OUTLETS:
        raise PlanError(f"outlets must be a list of 1 to {MAX_OUTLETS}")
    raw_tmvs = data.get("tmvs", [])
    if not isinstance(raw_tmvs, list) or len(raw_tmvs) > 20:
        raise PlanError("tmvs must be a list of at most 20")

    pipes: dict[str, Pipe] = {}
    for rp in raw_pipes:
        if not isinstance(rp, dict):
            raise PlanError("each pipe must be an object")
        pid = _ident(rp, "id")
        if pid in pipes:
            raise PlanError(f"pipe {pid} appears twice")
        material = rp.get("material", "copper")
        if material not in SIZES:
            raise PlanError(f"pipe {pid}: material must be copper or pex")
        dn = rp.get("dn", 15)
        if dn not in SIZES[material]:
            raise PlanError(f"pipe {pid}: dn must be one of {sorted(SIZES[material])}")
        zone = rp.get("zone")
        if zone not in ZONES:
            raise PlanError(f"pipe {pid}: zone must be one of {', '.join(ZONES)}")
        pts_raw = rp.get("points")
        if not isinstance(pts_raw, list) or not 2 <= len(pts_raw) <= 50:
            raise PlanError(f"pipe {pid}: points must list 2 to 50 corners")
        pts = [_point(p, f"pipe {pid} point") for p in pts_raw]
        drawn = sum(math.dist(a, b) for a, b in pairwise(pts))
        length = _num(rp, "length", 0.1, 200, max(0.1, round(drawn, 3)))
        source = _str(rp, "from", 30)
        pipes[pid] = Pipe(pid, source, length, int(dn), str(material), _num(rp, "insulation", 0, 50, 0), str(zone), pts)

    tmvs: dict[str, Tmv] = {}
    for rt in raw_tmvs:
        if not isinstance(rt, dict):
            raise PlanError("each tempering valve must be an object")
        tid = _ident(rt, "id")
        hot, cold = _str(rt, "hot", 24), _str(rt, "cold", 24)
        for side in (hot, cold):
            if side not in pipes:
                raise PlanError(f"tempering valve {tid}: no pipe {side}")
        tmvs[tid] = Tmv(tid, hot, cold, _num(rt, "set", 35, 55, 50), _point(rt.get("at"), f"tempering valve {tid}"))

    for p in pipes.values():
        s = p.source
        ok = s in ("hot", "cold") or (s.startswith("pipe:") and s[5:] in pipes) or (s.startswith("tmv:") and s[4:] in tmvs)
        if not ok:
            raise PlanError(f"pipe {p.id}: from must be hot, cold, pipe:<id> or tmv:<id>")

    b = Building(name, setpoint, pipes, tmvs, {}, [], (0, 0, 0), (0, 0, 0), (1, 1, 1))
    _classify(b)

    outlets: dict[str, Outlet] = {}
    for ro in raw_outlets:
        if not isinstance(ro, dict):
            raise PlanError("each outlet must be an object")
        oid = _ident(ro, "id")
        if oid in outlets:
            raise PlanError(f"outlet {oid} appears twice")
        kind = ro.get("kind")
        if kind not in KINDS:
            raise PlanError(f"outlet {oid}: kind must be one of {', '.join(KINDS)}")
        hot_ref, cold_ref = ro.get("hot"), ro.get("cold")
        for ref, want in ((hot_ref, ("hot", "tempered")), (cold_ref, ("cold",))):
            if ref is None:
                continue
            if not isinstance(ref, str) or ref not in pipes or pipes[ref].kind not in want:
                raise PlanError(f"outlet {oid}: hot must name a hot or tempered pipe and cold a cold pipe")
        if hot_ref is None and cold_ref is None:
            raise PlanError(f"outlet {oid} needs a hot or cold pipe")
        uses_raw = ro.get("uses", [])
        if not isinstance(uses_raw, list) or len(uses_raw) > MAX_USES:
            raise PlanError(f"outlet {oid}: uses must be a list of at most {MAX_USES}")
        uses = []
        for u in uses_raw:
            if not isinstance(u, dict):
                raise PlanError(f"outlet {oid}: each use must be an object")
            days = u.get("days", [0, 1, 2, 3, 4, 5, 6])
            if (
                not isinstance(days, list)
                or not days
                or not all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 6 for x in days)
            ):
                raise PlanError(f"outlet {oid}: days must list weekdays 0 (Monday) to 6")
            flush = u.get("flush", False)
            if not isinstance(flush, bool):
                raise PlanError(f"outlet {oid}: flush must be true or false")
            uses.append(Use(_num(u, "at", 0, 23.9), _num(u, "minutes", 0.1, 60), tuple(sorted(set(days))), flush))
        _, flow, temp = KINDS[str(kind)]
        outlets[oid] = Outlet(
            oid,
            _str(ro, "name", 40),
            str(kind),
            hot_ref,
            cold_ref,
            uses,
            _num(ro, "flow", 1, 30, flow),
            _num(ro, "temp", 10, 50, temp),
            _point(ro.get("at"), f"outlet {oid}"),
        )
    b.outlets = outlets

    rooms = []
    for rr in data.get("rooms", []) if isinstance(data.get("rooms", []), list) else []:
        if isinstance(rr, dict) and isinstance(rr.get("box"), list) and len(rr["box"]) == 4:
            box = rr["box"]
            if all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and abs(x) < 500 for x in box):
                rooms.append(Room(_str(rr, "name", 30), (float(box[0]), float(box[1]), float(box[2]), float(box[3]))))
    if len(rooms) > 60:
        raise PlanError("at most 60 rooms")
    b.rooms = rooms
    b.heater_at = _point(data.get("heater_at", [0, 0, 0]), "heater_at")
    b.meter_at = _point(data.get("meter_at", [0, 0, 0]), "meter_at")
    b.size = _point(data.get("size", [15, 10, 2.7]), "size")
    return b


def _classify(b: Building) -> None:
    """Labels each pipe hot, cold or tempered, and refuses loops and valves fed wrongly."""
    b.children = {pid: [] for pid in b.pipes}
    for p in b.pipes.values():
        if p.source.startswith("pipe:"):
            b.children[p.source[5:]].append(p.id)
    memo: dict[str, str] = {}

    def kind(pid: str, seen: frozenset[str]) -> str:
        if pid in memo:
            return memo[pid]
        if pid in seen:
            raise PlanError(f"the pipes loop back on themselves at {pid}")
        s = b.pipes[pid].source
        if s in ("hot", "cold"):
            k = s
        elif s.startswith("tmv:"):
            t = b.tmvs[s[4:]]
            if kind(t.hot, seen | {pid}) != "hot" or kind(t.cold, seen | {pid}) != "cold":
                raise PlanError(f"tempering valve {t.id} must be fed by a hot pipe and a cold pipe")
            k = "tempered"
        else:
            k = kind(s[5:], seen | {pid})
        memo[pid] = k
        return k

    for pid, p in b.pipes.items():
        p.kind = kind(pid, frozenset())
