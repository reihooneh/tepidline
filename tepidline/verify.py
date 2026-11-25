"""Checks of the model against exact answers and a finer model, reported on the method page."""

from __future__ import annotations

import math
import random
from typing import Any

from . import examples
from .model import load
from .physics import (
    COPPER_RHO_C,
    H_OUTSIDE,
    K_INSULATION,
    KILL_POINTS,
    SIZES,
    WATER_RHO_C,
    kill_rate,
    pipe_thermal,
    relax,
    warm_time,
    weight,
)
from .sim import Settings, Simulation, mix

FOAM_RHO_C = 0.06e6  # closed-cell foam, J/(m^3 K)


def _warm_numeric(t0: float, ta: float, tau: float, dt: float, n: int = 40000) -> float:
    return sum(weight(relax(t0, ta, tau, (i + 0.5) * dt / n)) for i in range(n)) * dt / n


def check_warm_time(cases: int = 300) -> dict[str, Any]:
    rng = random.Random(7)  # nosec B311
    worst = 0.0
    for _ in range(cases):
        a = (rng.uniform(5, 70), rng.uniform(5, 60), rng.uniform(600, 6000), rng.uniform(60, 30000))
        worst = max(worst, abs(warm_time(*a) - _warm_numeric(*a)))
    return {
        "name": "Warm hours: closed form against step-by-step integration",
        "detail": f"{cases} random cooling and warming curves",
        "value": round(worst, 2),
        "unit": "s largest difference",
        "pass": worst < 2.0,
    }


def radial_cooling(
    insulation_mm: float, t0: float = 60.0, ta: float = 22.0, hours: float = 6.0
) -> tuple[list[float], list[float]]:
    """A DN15 copper pipe cooling, with the lagging split into thin shells that store heat and pass
    it outwards (explicit finite differences). Returns times (s) and water temperatures."""
    od, wall = SIZES["copper"][15]
    r_o = od / 2
    r_i = r_o - wall
    c_core = WATER_RHO_C * math.pi * r_i**2 + COPPER_RHO_C * math.pi * (r_o**2 - r_i**2)
    n = 12 if insulation_mm > 0 else 0
    r_out = r_o + insulation_mm / 1000
    edges = [r_o + (r_out - r_o) * k / n for k in range(n + 1)] if n else [r_o]
    temps = [t0] + [t0] * n
    caps = [c_core] + [FOAM_RHO_C * math.pi * (edges[k + 1] ** 2 - edges[k] ** 2) for k in range(n)]
    # conductances between neighbours (core to first shell centre, shell to shell, last shell to air)
    mids = [(edges[k] + edges[k + 1]) / 2 for k in range(n)]
    cond = []
    if n:
        cond.append(2 * math.pi * K_INSULATION / math.log(mids[0] / r_o))
        for k in range(n - 1):
            cond.append(2 * math.pi * K_INSULATION / math.log(mids[k + 1] / mids[k]))
        g_air = 1 / (math.log(r_out / mids[-1]) / (2 * math.pi * K_INSULATION) + 1 / (H_OUTSIDE * 2 * math.pi * r_out))
    else:
        g_air = H_OUTSIDE * 2 * math.pi * r_o
    dt = 0.05 if n else 1.0
    times, water = [0.0], [t0]
    t, record = 0.0, 60.0
    while t < hours * 3600:
        flows = [0.0] * (n + 1)
        for k in range(n):
            q = cond[k] * (temps[k] - temps[k + 1])
            flows[k] -= q
            flows[k + 1] += q
        flows[n] -= g_air * (temps[n] - ta)
        for k in range(n + 1):
            temps[k] += flows[k] * dt / caps[k]
        t += dt
        if t >= record - 1e-9:
            times.append(t)
            water.append(temps[0])
            record += 60.0
    return times, water


def check_lumped() -> list[dict[str, Any]]:
    out = []
    for ins in (13.0,):
        times, water = radial_cooling(ins)
        tau = pipe_thermal("copper", 15, ins).tau
        lumped = [relax(60.0, 22.0, tau, t) for t in times]
        worst = max(abs(a - b) for a, b in zip(water, lumped))
        out.append(
            {
                "name": "A standing lagged pipe: one temperature against a layered model",
                "detail": "DN15 copper, 60 °C water in 22 °C air, 6 hours; the layered model lets the lagging store heat",
                "value": round(worst, 2),
                "unit": "°C largest difference",
                "pass": worst < 1.0,
                "curve": {
                    "t": [round(x / 3600, 3) for x in times[::5]],
                    "fine": [round(x, 2) for x in water[::5]],
                    "lumped": [round(x, 2) for x in lumped[::5]],
                },
            }
        )
    return out


def check_conservation() -> dict[str, Any]:
    b = load(examples.family_house())
    sim = Simulation(b, Settings(record_day=-1))
    sim.run()
    worst = max(abs(sum(p[0] for p in q) - sim.vols[pid]) / sim.vols[pid] for pid, q in sim.state.items())
    drawn = sum(r.litres for r in sim.outlets.values())
    expected = 0.0
    for o in b.outlets.values():
        for u in o.uses:
            days = sum(1 for d in range(1, 8) if d % 7 in u.days)
            expected += o.flow * u.minutes * days
    ok = worst < 1e-9 and abs(drawn - expected) < 1e-6 * expected
    return {
        "name": "Water is neither made nor lost",
        "detail": f"every pipe still holds exactly its volume after a week; {drawn:,.0f} L drawn, as scheduled",
        "value": f"{worst:.0e}",
        "unit": "largest relative error",
        "pass": ok,
    }


def check_mixing() -> dict[str, Any]:
    hot = [0.6, 60.0, 0.0, 0.0, 0.0]
    cold = [0.4, 22.0, 18000.0, 0.0, 0.0]
    m = mix([hot, cold])
    energy = hot[0] * hot[1] + cold[0] * cold[1]
    ok = abs(m[0] - 1.0) < 1e-12 and abs(m[0] * m[1] - energy) < 1e-9 and m[2] == 18000.0
    return {
        "name": "Mixing keeps volume and heat",
        "detail": "0.6 L at 60 °C with 0.4 L at 22 °C gives 1 L at 44.8 °C; "
        "the cold water's warm hours are kept (it is two fifths of the mix)",
        "value": round(m[1], 2),
        "unit": "°C",
        "pass": ok,
    }


def check_kill_rates() -> dict[str, Any]:
    worst = max(abs(kill_rate(t) * 3600 - k) / k for t, k in KILL_POINTS)
    return {
        "name": "Heat inactivation passes through the measured rates",
        "detail": "Sanden et al. 1989 at 45, 50, 55 and 60 °C",
        "value": f"{worst:.0e}",
        "unit": "largest relative error",
        "pass": worst < 1e-9,
    }


def run() -> dict[str, Any]:
    checks = [check_warm_time(), *check_lumped(), check_conservation(), check_mixing(), check_kill_rates()]
    return {"checks": checks}
