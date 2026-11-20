"""Pipe heat loss, the time water spends in the 25-45 °C band, and heat treatment above 45 °C.

All times are in seconds and temperatures in °C. A stagnant pipe is a lumped body: the water and
the pipe wall share one temperature that relaxes exponentially towards the air around the pipe,
T(t) = Ta + (T0 - Ta) exp(-t / tau), with tau = C' / U' per metre of pipe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

BAND_LO = 25.0  # °C: the range guidance uses for Legionella growth (Heida et al. 2022; CDC)
BAND_HI = 45.0
# How much an hour at each temperature counts towards "warm hours": nothing outside the band, in
# full across its middle, ramping at the edges so water that only just touches 25 °C (a wall in
# summer) or 45 °C counts for little. The ramps are Tepidline's screening choice, not a growth curve.
WEIGHT: tuple[tuple[float, float], ...] = ((25.0, 0.0), (30.0, 1.0), (40.0, 1.0), (45.0, 0.0))
WATER_RHO_C = 4.18e6  # J/(m^3 K)
COPPER_RHO_C = 3.45e6  # J/(m^3 K)
PEX_RHO_C = 1.9e6  # J/(m^3 K)
K_COPPER = 390.0
K_PEX = 0.41
K_INSULATION = 0.035  # closed-cell foam lagging, W/(m K)
H_OUTSIDE = 8.0  # still air, convection plus radiation, W/(m^2 K)

# Nominal sizes: (outside diameter, wall) in metres. Copper to AS 1432 type B, PEX-AL-PEX to suit.
SIZES: dict[str, dict[int, tuple[float, float]]] = {
    "copper": {15: (0.01270, 0.00091), 18: (0.01588, 0.00091), 20: (0.01905, 0.00107), 25: (0.02540, 0.00122)},
    "pex": {15: (0.01600, 0.00200), 18: (0.02000, 0.00200), 20: (0.02000, 0.00200), 25: (0.02500, 0.00250)},
}

# First-order heat inactivation rates of L. pneumophila in water (per hour), Sanden et al. 1989,
# as tabulated by Cazals et al. 2022. Below 45 °C there is no inactivation.
KILL_POINTS: tuple[tuple[float, float], ...] = ((45.0, 0.024), (50.0, 0.16), (55.0, 4.3), (60.0, 81.0))
_LN10 = math.log(10.0)


@dataclass(frozen=True)
class PipeThermal:
    volume_per_m: float  # m^3/m of water
    capacity_per_m: float  # J/(K m), water and wall
    conductance_per_m: float  # W/(K m) to the surrounding air

    @property
    def tau(self) -> float:
        return self.capacity_per_m / self.conductance_per_m


def pipe_thermal(material: str, dn: int, insulation_mm: float) -> PipeThermal:
    """Per-metre volume, heat capacity and heat-loss conductance of a pipe."""
    od, wall = SIZES[material][dn]
    r_o = od / 2
    r_i = r_o - wall
    area = math.pi * r_i * r_i
    wall_area = math.pi * (r_o * r_o - r_i * r_i)
    rho_c = COPPER_RHO_C if material == "copper" else PEX_RHO_C
    k_wall = K_COPPER if material == "copper" else K_PEX
    resistance = math.log(r_o / r_i) / (2 * math.pi * k_wall)  # (m K)/W
    r_out = r_o
    if insulation_mm > 0:
        r_out = r_o + insulation_mm / 1000
        resistance += math.log(r_out / r_o) / (2 * math.pi * K_INSULATION)
    resistance += 1 / (H_OUTSIDE * 2 * math.pi * r_out)
    return PipeThermal(area, WATER_RHO_C * area + rho_c * wall_area, 1 / resistance)


def relax(t0: float, ambient: float, tau: float, dt: float) -> float:
    """Temperature after dt seconds of standing still."""
    return ambient + (t0 - ambient) * math.exp(-dt / tau)


def _reach(target: float, t0: float, ambient: float, tau: float) -> float:
    """Seconds until the exponential first reaches `target`; inf if it never does."""
    d = t0 - ambient
    r = (target - ambient) / d
    if r <= 0 or r > 1:
        return math.inf
    return -tau * math.log(r)


def weight(temp: float) -> float:
    """How much an hour at this temperature counts towards warm hours (0 to 1)."""
    pts = WEIGHT
    if temp <= pts[0][0] or temp >= pts[-1][0]:
        return 0.0
    for (ta, wa), (tb, wb) in pairwise(pts):
        if temp <= tb:
            return wa + (wb - wa) * (temp - ta) / (tb - ta)
    return 0.0


def warm_time(t0: float, ambient: float, tau: float, dt: float) -> float:
    """Exact integral over [0, dt] of weight(T(t)) for the relaxing temperature, in seconds.

    The weight is piecewise linear in temperature, so between the moments T crosses a corner of
    the weight it integrates in closed form: the integral of T(t) is Ta*t - D*tau*exp(-t/tau).
    """
    if dt <= 0:
        return 0.0
    d = t0 - ambient
    if abs(d) < 1e-9:
        return weight(t0) * dt
    t1 = ambient + d * math.exp(-dt / tau)
    lo, hi = (t1, t0) if d > 0 else (t0, t1)
    if hi <= WEIGHT[0][0] or lo >= WEIGHT[-1][0]:
        return 0.0  # never in the band
    if WEIGHT[1][0] <= lo and hi <= WEIGHT[2][0]:
        return dt  # in the middle of the band throughout
    cuts = [0.0, dt]
    for corner, _ in WEIGHT:
        c = _reach(corner, t0, ambient, tau)
        if 0.0 < c < dt:
            cuts.append(c)
    cuts.sort()
    total = 0.0
    for a, b in pairwise(cuts):
        if b - a <= 0:
            continue
        tm = ambient + d * math.exp(-(a + b) / 2 / tau)
        if tm <= WEIGHT[0][0] or tm >= WEIGHT[-1][0]:
            continue
        for (ta_, wa), (tb_, wb) in pairwise(WEIGHT):
            if tm <= tb_:
                slope = (wb - wa) / (tb_ - ta_)
                break
        intercept = wa - slope * ta_
        integral_t = ambient * (b - a) + d * tau * (math.exp(-a / tau) - math.exp(-b / tau))
        total += intercept * (b - a) + slope * integral_t
    return max(0.0, total)


_KILL_T = [t for t, _ in KILL_POINTS]
_KILL_LN = [math.log(k / 3600.0) for _, k in KILL_POINTS]
_KILL_SLOPE = [(_KILL_LN[i + 1] - _KILL_LN[i]) / (_KILL_T[i + 1] - _KILL_T[i]) for i in range(len(KILL_POINTS) - 1)]
KILL_CAP = 70.0  # above this the rate is held: it is already effectively instant


def kill_rate(temp: float) -> float:
    """Heat inactivation rate (per second, natural log) at a temperature: log-linear between the
    measured points, extended past 60 °C with the last slope."""
    if temp < 45.0:
        return 0.0
    if temp >= 60.0:
        return math.exp(_KILL_LN[3] + _KILL_SLOPE[2] * (min(temp, KILL_CAP) - 60.0))
    i = 0 if temp < 50.0 else (1 if temp < 55.0 else 2)
    return math.exp(_KILL_LN[i] + _KILL_SLOPE[i] * (temp - _KILL_T[i]))


def log_reduction(t0: float, ambient: float, tau: float, dt: float) -> float:
    """log10 reduction from heat over dt seconds of relaxing (Simpson's rule on 6 intervals)."""
    if dt <= 0:
        return 0.0
    e = math.exp(-dt / tau)
    t1 = ambient + (t0 - ambient) * e
    if t0 < 45.0 and t1 < 45.0:
        return 0.0
    if abs(t0 - ambient) < 0.05:
        return kill_rate(t0) * dt / _LN10
    n = 6
    h = dt / n
    r = math.exp(-h / tau)
    d = t0 - ambient
    total = 0.0
    for i in range(n + 1):
        w = 1 if i in (0, n) else (4 if i % 2 else 2)
        total += w * kill_rate(ambient + d)
        d *= r
    return total * h / 3 / _LN10
