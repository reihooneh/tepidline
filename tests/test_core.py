"""Tests for the Tepidline core."""

from __future__ import annotations

import copy
import json
import math
import random
from itertools import pairwise

import pytest

from tepidline import api, examples, fixes
from tepidline.model import PlanError, load
from tepidline.physics import kill_rate, log_reduction, pipe_thermal, relax, warm_time, weight
from tepidline.sim import Settings, Simulation, simulate


@pytest.fixture(scope="module")
def house() -> dict:
    return examples.family_house()


@pytest.fixture(scope="module")
def summer(house: dict) -> dict:
    return simulate(load(house), Settings(record_day=2))


# ------------------------------------------------------------------ physics


def numeric_warm(t0: float, ta: float, tau: float, dt: float, n: int = 20000) -> float:
    return sum(weight(relax(t0, ta, tau, (i + 0.5) * dt / n)) for i in range(n)) * dt / n


def test_warm_time_is_exact() -> None:
    rng = random.Random(1)
    for _ in range(300):
        a = (rng.uniform(0, 75), rng.uniform(0, 60), rng.uniform(300, 9000), rng.uniform(1, 50000))
        assert warm_time(*a) == pytest.approx(numeric_warm(*a), abs=a[3] * 1e-4 + 0.5)


def test_warm_time_edges() -> None:
    assert warm_time(35, 35, 1000, 3600) == 3600  # held in the middle of the band
    assert warm_time(20, 20, 1000, 3600) == 0
    assert warm_time(70, 50, 1000, 3600) == 0  # never comes down to 45
    assert warm_time(60, 20, 1000, 0) == 0
    assert weight(27.5) == pytest.approx(0.5)
    assert weight(42.5) == pytest.approx(0.5)


def test_lagging_slows_a_pipe() -> None:
    bare, lagged = pipe_thermal("copper", 15, 0), pipe_thermal("copper", 15, 13)
    assert lagged.tau > 1.8 * bare.tau
    assert bare.volume_per_m * 1000 == pytest.approx(0.093, abs=0.002)  # DN15 copper holds about 93 mL a metre


def test_heat_treatment() -> None:
    assert kill_rate(44.9) == 0
    assert kill_rate(60) * 3600 == pytest.approx(81)
    assert kill_rate(50) * 3600 == pytest.approx(0.16)
    held = log_reduction(60, 60, 1e9, 600)
    assert held == pytest.approx(81 / 3600 * 600 / math.log(10), rel=1e-6)
    assert log_reduction(40, 20, 1000, 3600) == 0


# ------------------------------------------------------------------ plans


def test_examples_load() -> None:
    for make in examples.EXAMPLES.values():
        b = load(make())
        assert b.outlets and b.pipes
        kinds = {p.kind for p in b.pipes.values()}
        assert {"hot", "cold", "tempered"} <= kinds


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(pipes="no"), "pipes must be a list"),
        (lambda d: d["pipes"][0].update(zone="attic"), "zone must be"),
        (lambda d: d["pipes"][0].update(dn=13), "dn must be"),
        (lambda d: d["pipes"][0].update(points=[[0, 0, float("nan")], [1, 1, 1]]), "point"),
        (lambda d: d["pipes"][0].update(points=[[0, 0, 0], [1e9, 1, 1]]), "point"),
        (lambda d: d["pipes"][0].update(length=1e6), "length"),
        (lambda d: d["pipes"][0].update(id="a<b>"), "letters"),
        (lambda d: d["pipes"][0].update({"from": "pipe:nowhere"}), "from must be"),
        (lambda d: d["pipes"].append(dict(d["pipes"][0])), "appears twice"),
        (lambda d: d["outlets"][0].update(kind="hose"), "kind must be"),
        (lambda d: d["outlets"][0].update(hot="c-main"), "hot must name"),
        (lambda d: d["outlets"][0]["uses"].append({"at": 25, "minutes": 1}), "at must be"),
        (lambda d: d["outlets"][0]["uses"].append({"at": 5, "minutes": 1, "days": [7]}), "days"),
        (lambda d: d["outlets"][0].update(name="x\u0000y"), "short piece of text"),
        (lambda d: d.update(setpoint=True), "setpoint"),
        (lambda d: d["tmvs"][0].update(hot="c-tmv"), "fed by a hot pipe"),
    ],
)
def test_bad_plans_are_refused(house: dict, change, message: str) -> None:  # type: ignore[no-untyped-def]
    d = copy.deepcopy(house)
    change(d)
    with pytest.raises(PlanError, match=message):
        load(d)


def test_loops_are_refused(house: dict) -> None:
    d = copy.deepcopy(house)
    pipes = {p["id"]: p for p in d["pipes"]}
    pipes["h-out"]["from"] = "pipe:h-kitchen"
    with pytest.raises(PlanError, match="loop"):
        load(d)


def test_limits(house: dict) -> None:
    d = copy.deepcopy(house)
    d["pipes"] = d["pipes"] * 10
    with pytest.raises(PlanError):
        load(d)
    assert json.loads(api.call("[" * 5000))["ok"] is False
    assert json.loads(api.call("x" * 3_000_000))["ok"] is False
    assert json.loads(api.call(json.dumps({"op": "check", "plan": {"name": "x"}})))["ok"] is False
    assert json.loads(api.call(json.dumps({"op": "rm -rf"})))["error"] == "unknown request"
    bad = json.loads(api.call(json.dumps({"op": "apply", "plan": "house", "fixes": ["__import__"]})))
    assert bad == {"ok": False, "error": "unknown fix"}


# ------------------------------------------------------------------ simulation


def test_water_is_conserved(house: dict) -> None:
    b = load(house)
    s = Simulation(b, Settings(record_day=-1))
    s.run()
    for pid, q in s.state.items():
        assert sum(p[0] for p in q) == pytest.approx(s.vols[pid], rel=1e-9)
    expected = sum(
        o.flow * u.minutes * sum(1 for d in range(1, 8) if d % 7 in u.days) for o in b.outlets.values() for u in o.uses
    )
    assert sum(r.litres for r in s.outlets.values()) == pytest.approx(expected, rel=1e-9)


def test_tempering_valve_holds_its_set_temperature(house: dict) -> None:
    b = load(house)
    s = Simulation(b, Settings(record_day=-1))
    out = s.feed("tmv:tmv", 0.001, 7 * 3600.0)
    assert out[0][1] == pytest.approx(50.0, abs=0.01)


def test_summer_house_findings(summer: dict) -> None:
    o = summer["outlets"]
    # the guest bathroom's water waits all week
    assert o["guest-shower"]["worst_hours"] > 20
    # the everyday showers draw water that sat warm through the afternoon in the roof
    assert o["main-shower"]["risky_litres"] > 5
    # the kitchen's short hot pipe under the floor stays out of the band
    assert o["kitchen"]["risky_litres"] < o["main-shower"]["risky_litres"]
    assert len(summer["snapshots"]["t"]) == 48
    assert summer["outlets"]["main-shower"]["first_draw"]


def test_winter_is_safer(house: dict, summer: dict) -> None:
    winter = simulate(load(house), Settings(season="winter", record_day=-1))
    assert winter["score"] < 0.5 * summer["score"]


def test_coming_home_after_a_week_away(house: dict) -> None:
    away = simulate(load(house), Settings(scenario="away", record_day=-1))
    assert away["outlets"]["main-shower"]["worst_hours"] > 30


def test_care_wing_tempered_ceiling_runs() -> None:
    r = simulate(load(examples.care_wing()), Settings(record_day=-1))
    assert r["outlets"]["r4-shower"]["worst_hours"] > r["outlets"]["r1-shower"]["worst_hours"]  # the empty room


# ------------------------------------------------------------------ fixes


def test_candidates_and_groups(house: dict) -> None:
    fx = fixes.candidates(house)
    ids = {f.id for f in fx}
    assert {"lag-hot", "move-hot", "lag-cold", "move-cold", "pou-tmv", "hotter", "habit", "flush", "cap"} <= ids
    combos = fixes.combinations(fx)
    assert len(combos) == 3 * 3 * 2 * 2 * 4
    for c in combos:
        groups = [next(f.group for f in fx if f.id == i) for i in c]
        assert len(groups) == len(set(groups))


def test_point_of_use_valves(house: dict) -> None:
    d, _ = fixes.apply(house, ["pou-tmv"])
    b = load(d)
    assert "tmv" not in b.tmvs
    assert len(b.tmvs) == 3  # ensuite, guest bathroom, bathroom
    for o in b.outlets.values():
        if o.kind in ("shower", "basin", "bath"):
            assert o.hot and b.pipes[o.hot].kind == "tempered" and b.pipes[o.hot].length < 1
    assert "c-tmv" not in b.pipes  # the old valve's cold feed is capped


def test_capping_prunes_pipes(house: dict) -> None:
    d, _ = fixes.apply(house, ["cap"])
    b = load(d)
    assert "guest-shower" not in b.outlets and "laundry" in b.outlets
    assert not any(pid.startswith(("t-g-", "c-g-")) for pid in b.pipes)


def test_moving_cold_pipes_out_of_the_roof_helps(house: dict, summer: dict) -> None:
    d, extra = fixes.apply(house, ["move-cold"])
    after = simulate(load(d), Settings(record_day=-1), extra)
    assert after["score"] < 0.6 * summer["score"]


def test_plan_tries_everything_and_the_frontier_is_sound() -> None:
    small = examples.family_house()
    small["outlets"] = [o for o in small["outlets"] if o["id"] in ("main-shower", "kitchen", "guest-shower")]
    res = fixes.plan(small, Settings(record_day=-1))
    assert len(res["combos"]) == len(fixes.combinations(fixes.candidates(small)))
    front = res["frontier"]
    assert front[0]["cost"] == 0
    for a, b in pairwise(front):
        assert b["cost"] > a["cost"] and b["score"] < a["score"]
    for budget in (0, 500, 1000, 3000, 10000):
        best = fixes.best_for(res, budget)
        assert best["cost"] <= budget
        cheaper = [r["score"] for r in res["combos"] if r["cost"] <= budget]
        assert best["score"] <= min(cheaper) + max(0.05, 0.005 * best["score"]) + 1e-9


def test_api_round_trip() -> None:
    out = json.loads(api.call(json.dumps({"op": "check", "plan": "care", "settings": {"season": "winter"}})))
    assert out["ok"] and out["building"]["name"] == "Aged-care wing"
    assert set(out["result"]["outlets"]) == set(out["building"]["outlets"])
    bad = json.loads(api.call(json.dumps({"op": "check", "plan": "house", "settings": {"season": "monsoon"}})))
    assert bad["ok"] is False
