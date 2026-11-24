"""Follows every drop of water through a building's pipes for a week.

Water moves as plug flow: each pipe holds a queue of parcels (volume, temperature, hours in the
25-45 °C band, heat treatment received, age). When a tap runs, parcels leave the end of its pipe
and every pipe upstream shifts along by the same volume, fed at the top by the water heater, the
mains or a tempering valve that mixes hot and cold to its set temperature. Standing water relaxes
towards the air around the pipe (exactly, between events), and the time it spends in the band is
counted exactly. Water that gets hot enough for long enough (2 log10 of heat inactivation, from
measured rates) starts counting from zero again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .climate import DAY, Climate
from .model import Building
from .physics import log_reduction, relax, warm_time

TICK = 1800.0  # every pipe is brought up to date at least this often (s)
STEP = 10.0  # a running tap moves water in steps of this many seconds for its first minute,
LONG_STEP = 60.0  # and then of this many (by then the water that stood in the pipes has gone)
MAX_PARCELS = 10
RESET_LOGS = 2.0  # log10 of heat inactivation that counts as heat-treated
HOT_ARRIVES = 40.0  # °C on the hot side: "the hot water's here"
SAMPLES = 6  # points along each pipe recorded for the 3D view

# A parcel: [volume m^3, temperature °C, seconds in band, log10 heat treatment, age s]
Parcel = list[float]


@dataclass(frozen=True)
class Settings:
    season: str = "summer"
    roof: str = "dark"
    setpoint: float | None = None  # water heater; None keeps the plan's
    tmv_set: float | None = None  # all tempering valves; None keeps each valve's
    scenario: str = "normal"  # normal, or away: nobody home for six days, back on the seventh
    risk_hours: float = 4.0  # water that has sat this long in the band counts as risky
    days: int = 8  # day 0 settles the pipes; days 1 to 7 are measured
    record_day: int = 2  # the day kept for the 3D view (-1: none)


@dataclass
class OutletResult:
    risky_litres: float = 0.0
    litres: float = 0.0
    worst_hours: float = 0.0
    draws: int = 0
    wait_litres: float = 0.0  # mixed water run before hot arrives, summed over draws
    first_draw: list[list[float]] = field(default_factory=list)


@dataclass
class PipeResult:
    band_seconds: float = 0.0
    worst_hours: float = 0.0


class Simulation:
    def __init__(self, b: Building, s: Settings, extra_uses: dict[str, list[tuple[float, float]]] | None = None) -> None:
        self.b, self.s = b, s
        self.clim = Climate(s.season, s.roof)
        self.setpoint = s.setpoint if s.setpoint is not None else b.setpoint
        self.mains = self.clim.mains
        self.risk = s.risk_hours * 3600
        self.state: dict[str, list[Parcel]] = {}
        self.t_at: dict[str, float] = {}
        self.taus = {pid: p.thermal.tau for pid, p in b.pipes.items()}
        self.vols = {pid: p.volume for pid, p in b.pipes.items()}
        self.zone = {pid: p.zone for pid, p in b.pipes.items()}
        self.pipes = {pid: PipeResult() for pid in b.pipes}
        self.outlets = {oid: OutletResult() for oid in b.outlets}
        self.measuring = False
        self.extra = extra_uses or {}
        self.snap_t: list[float] = []
        self.snaps: dict[str, list[list[float]]] = {pid: [] for pid in b.pipes}
        self.snap_air: dict[str, list[float]] = {z: [] for z in ("roof", "outdoor", "indoor", "underfloor")}
        for pid, p in b.pipes.items():
            start = self.mains if p.kind == "cold" else self.clim.air(p.zone, 0)
            self.state[pid] = [[self.vols[pid], start, 0.0, 0.0, 0.0]]
            self.t_at[pid] = 0.0

    # ------------------------------------------------------------ standing water
    def advance(self, pid: str, t: float) -> None:
        dt = t - self.t_at[pid]
        if dt <= 0:
            return
        tau = self.taus[pid]
        ta = self.clim.air(self.zone[pid], self.t_at[pid] + dt / 2)
        vol = self.vols[pid]
        res = self.pipes[pid]
        for par in self.state[pid]:
            t0 = par[1]
            bt = warm_time(t0, ta, tau, dt)
            if self.measuring:
                res.band_seconds += bt * par[0] / vol
            par[2] += bt
            if par[2] > 0.0 and (t0 > 45.0 or ta > 45.0):
                par[3] += log_reduction(t0, ta, tau, dt)
                if par[3] >= RESET_LOGS:
                    par[2] = 0.0
                    par[3] = 0.0
            par[1] = relax(t0, ta, tau, dt)
            par[4] += dt
            if par[2] > res.worst_hours * 3600 and self.measuring:
                res.worst_hours = par[2] / 3600
        self.t_at[pid] = t

    # ------------------------------------------------------------ moving water
    def tail_temp(self, pid: str, t: float) -> float:
        self.advance(pid, t)
        return self.state[pid][-1][1]

    def profile(self, source: str, vmax: float, t: float) -> list[tuple[float, float]]:
        """(volume, temperature) of the next vmax of water a source would deliver, first out first."""
        if source == "hot":
            return [(vmax, self.setpoint)]
        if source == "cold":
            return [(vmax, self.mains)]
        if source.startswith("tmv:"):
            tmv = self.b.tmvs[source[4:]]
            return [(vmax, self.s.tmv_set if self.s.tmv_set is not None else tmv.set)]
        pid = source[5:] if source.startswith("pipe:") else source
        self.advance(pid, t)
        out: list[tuple[float, float]] = []
        got = 0.0
        for par in reversed(self.state[pid]):
            take = min(par[0], vmax - got)
            out.append((take, par[1]))
            got += take
            if got >= vmax * (1 - 1e-12):
                return out
        return out + self.profile(self.b.pipes[pid].source, vmax - got, t)

    def mix_fraction(self, hot: str, cold: str, target: float, dv: float, t: float) -> float:
        """The share of hot water that brings the mix to `target`, as a thermostatic valve (or a
        person at a mixer) settles on over the step, given what each side is about to deliver."""
        ph, pc = self.profile(hot, dv, t), self.profile(cold, dv, t)
        if len(ph) == 1 and len(pc) == 1:  # each side delivers one temperature: solve directly
            th, tc = ph[0][1], pc[0][1]
            return 1.0 if th <= tc else min(1.0, max(0.0, (target - tc) / (th - tc)))

        def mean(prof: list[tuple[float, float]], v: float) -> float:
            if v <= 0:
                return prof[0][1]
            got, heat = 0.0, 0.0
            for vol, temp in prof:
                take = min(vol, v - got)
                heat += take * temp
                got += take
                if got >= v:
                    break
            return heat / got

        def mixed(f: float) -> float:
            return f * mean(ph, f * dv) + (1 - f) * mean(pc, (1 - f) * dv)

        if mixed(1.0) <= target:
            return 1.0
        if mixed(0.0) >= target:
            return 0.0
        lo, hi = 0.0, 1.0
        for _ in range(14):
            mid = (lo + hi) / 2
            if mixed(mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def feed(self, source: str, dv: float, t: float) -> list[Parcel]:
        if source == "hot":
            return [[dv, self.setpoint, 0.0, 0.0, 0.0]]
        if source == "cold":
            return [[dv, self.mains, 0.0, 0.0, 0.0]]
        if source.startswith("pipe:"):
            return self.pull(source[5:], dv, t)
        tmv = self.b.tmvs[source[4:]]
        target = self.s.tmv_set if self.s.tmv_set is not None else tmv.set
        f = self.mix_fraction(tmv.hot, tmv.cold, target, dv, t)
        parts = (self.pull(tmv.hot, f * dv, t) if f > 0 else []) + (self.pull(tmv.cold, (1 - f) * dv, t) if f < 1 else [])
        return [mix(parts)]

    def pull(self, pid: str, dv: float, t: float) -> list[Parcel]:
        """Moves dv of water out of the end of pipe pid; returns it, first out first."""
        self.advance(pid, t)
        inflow = self.feed(self.b.pipes[pid].source, dv, t)
        q = self.state[pid]
        q[0:0] = inflow[::-1]
        out: list[Parcel] = []
        need = dv
        while need > 1e-12 and q:
            par = q[-1]
            if par[0] <= need * (1 + 1e-9):
                out.append(q.pop())
                need -= par[0]
            else:
                part = par.copy()
                part[0] = need
                par[0] -= need
                out.append(part)
                need = 0.0
        tidy(q)
        return out

    # ------------------------------------------------------------ running a tap
    def draw_step(
        self,
        oid: str,
        dv_total: float,
        t: float,
        first: list[list[float]] | None,
        since: float,
        waiting: list[bool],
        count: bool = True,
    ) -> None:
        o = self.b.outlets[oid]
        res = self.outlets[oid]
        if o.hot and o.cold:
            th = self.tail_temp(o.hot, t)
            f = self.mix_fraction(o.hot, o.cold, o.temp, dv_total, t)
        else:
            f = 1.0 if o.hot else 0.0
            th = self.tail_temp(o.hot, t) if o.hot else 0.0
        parts: list[Parcel] = []
        if f > 0 and o.hot:
            parts += self.pull(o.hot, f * dv_total, t)
        if f < 1 and o.cold:
            parts += self.pull(o.cold, (1 - f) * dv_total, t)
        if not self.measuring or not count:
            return
        litres = dv_total * 1000
        res.litres += litres
        for par in parts:
            if par[2] >= self.risk:
                res.risky_litres += par[0] * 1000
            if par[2] / 3600 > res.worst_hours and par[0] > 1e-5:
                res.worst_hours = par[2] / 3600
        if o.hot and waiting[0]:
            if th >= HOT_ARRIVES:
                waiting[0] = False
            else:
                res.wait_litres += litres
        if first is not None:
            m = mix(parts) if parts else [0, 0, 0, 0, 0]
            first.append([round(since, 1), round(m[1], 2), round(max(p[2] for p in parts) / 3600 if parts else 0, 2)])

    # ------------------------------------------------------------ the week
    def schedule(self) -> list[tuple[float, float, str, bool]]:
        """Every draw in the week: (start, seconds, outlet, flush). Flushes run water to waste with
        nobody in the spray, so their water isn't counted as reaching anyone. Automatic flushing
        valves run whether or not anyone is home."""
        draws: list[tuple[float, float, str, bool]] = []
        for d in range(self.s.days):
            home = self.s.scenario != "away" or d == 0 or d == self.s.days - 1
            weekday = d % 7
            for oid, o in self.b.outlets.items():
                if home:
                    for u in o.uses:
                        if weekday in u.days:
                            draws.append((d * DAY + u.at * 3600, u.minutes * 60, oid, u.flush))
                for at, minutes in self.extra.get(oid, []):
                    draws.append((d * DAY + at * 3600, minutes * 60, oid, True))
        draws.sort()
        return draws

    def run(self) -> dict[str, Any]:
        draws = self.schedule()
        end = self.s.days * DAY
        events: list[tuple[float, int, str, float, float]] = []  # time, order, outlet, dv, since start
        for start, dur, oid, flush in draws:
            q = self.b.outlets[oid].flow / 60000  # m^3/s
            k = 0.0
            while k < dur - 1e-9:
                step = min(STEP if k < 60.0 else LONG_STEP, dur - k)
                events.append((start + k, 2 if flush else 1, oid, q * step, k))
                k += step
        t = TICK
        while t <= end + 1e-9:
            events.append((t, 0, "", 0.0, 0.0))
            t += TICK
        events.sort(key=lambda e: (e[0], e[1]))
        first_start: dict[str, float] = {}
        waiting: dict[tuple[str, float], list[bool]] = {}
        record = self.s.record_day
        for when, kind, oid, dv, since in events:
            day = int(when // DAY)
            self.measuring = day >= 1
            if kind == 0:
                for pid in self.state:
                    self.advance(pid, when)
                if record >= 0 and record * DAY < when <= (record + 1) * DAY:
                    self.snapshot(when)
                continue
            start = when - since
            if kind == 2:  # a flush: the water moves, but nobody receives it
                self.draw_step(oid, dv, when, None, since, [False], count=False)
                continue
            if since == 0.0:
                if self.measuring:
                    self.outlets[oid].draws += 1
                if day == record and oid not in first_start:
                    first_start[oid] = start
            first = self.outlets[oid].first_draw if first_start.get(oid) == start else None
            self.draw_step(oid, dv, when, first, since, waiting.setdefault((oid, start), [True]))
        return self.result()

    def snapshot(self, t: float) -> None:
        self.snap_t.append(t)
        for zone, temps in self.snap_air.items():
            temps.append(round(self.clim.air(zone, t), 1))
        for pid, q in self.state.items():
            vol = self.vols[pid]
            temps = []
            acc, i = 0.0, 0
            for k in range(SAMPLES):
                x = (k + 0.5) / SAMPLES * vol
                while i < len(q) - 1 and acc + q[i][0] < x:
                    acc += q[i][0]
                    i += 1
                temps.append(round(q[i][1], 1))
            self.snaps[pid].append(temps)

    def result(self) -> dict[str, Any]:
        days = 1 if self.s.scenario == "away" else self.s.days - 1
        outlets = {}
        score = 0.0
        for oid, r in self.outlets.items():
            o = self.b.outlets[oid]
            weekly = r.risky_litres * (7 / days if self.s.scenario != "away" else 1)
            outlets[oid] = {
                "risky_litres": round(weekly, 3),
                "litres": round(r.litres, 1),
                "worst_hours": round(r.worst_hours, 2),
                "draws": r.draws,
                "wait_litres": round(r.wait_litres / r.draws, 2) if r.draws else 0.0,
                "weight": o.weight,
                "first_draw": r.first_draw,
            }
            score += o.weight * weekly
        pipes = {
            pid: {"band_hours": round(r.band_seconds / 3600 / (self.s.days - 1), 2), "worst_hours": round(r.worst_hours, 2)}
            for pid, r in self.pipes.items()
        }
        out: dict[str, Any] = {"score": round(score, 3), "outlets": outlets, "pipes": pipes}
        if self.snap_t:
            out["snapshots"] = {
                "t": [round(x - self.s.record_day * DAY) for x in self.snap_t],
                "pipes": self.snaps,
                "air": self.snap_air,
            }
        return out


def mix(parts: list[Parcel]) -> Parcel:
    """One parcel from several: volumes add, temperature and age average by volume, and the band
    hours of any part making up a fifth or more are kept (the cautious choice)."""
    vol = sum(p[0] for p in parts)
    if vol <= 0:
        return [0.0, parts[0][1] if parts else 0.0, 0.0, 0.0, 0.0]
    temp = sum(p[0] * p[1] for p in parts) / vol
    band = max((p[2] for p in parts if p[0] >= 0.2 * vol), default=0.0)
    logs = sum(p[0] * p[3] for p in parts) / vol
    age = sum(p[0] * p[4] for p in parts) / vol
    return [vol, temp, band, logs, age]


def blend(a: Parcel, b: Parcel) -> Parcel:
    """Two neighbouring parcels as one, everything averaged by volume."""
    v = a[0] + b[0]
    wa, wb = a[0] / v, b[0] / v
    return [v, wa * a[1] + wb * b[1], wa * a[2] + wb * b[2], wa * a[3] + wb * b[3], wa * a[4] + wb * b[4]]


def tidy(q: list[Parcel]) -> None:
    """Merges neighbouring parcels that are alike, and the most alike pair while there are too many."""
    i = 0
    while i < len(q) - 1:
        a, b = q[i], q[i + 1]
        if abs(a[1] - b[1]) < 0.2 and abs(a[2] - b[2]) < 300 and abs(a[3] - b[3]) < 0.05:
            q[i] = blend(a, b)
            del q[i + 1]
        else:
            i += 1
    while len(q) > MAX_PARCELS:
        best, k = float("inf"), 0
        for j in range(len(q) - 1):
            a, b = q[j], q[j + 1]
            d = abs(a[1] - b[1]) + abs(a[2] - b[2]) / 1800 + min(a[0], b[0]) * 2000
            if d < best:
                best, k = d, j
        q[k : k + 2] = [blend(q[k], q[k + 1])]


def simulate(
    b: Building, s: Settings | None = None, extra_uses: dict[str, list[tuple[float, float]]] | None = None
) -> dict[str, Any]:
    return Simulation(b, s or Settings(), extra_uses).run()
