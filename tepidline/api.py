"""JSON in, JSON out: what the command line and the web page call."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any

from . import examples, fixes
from .model import Building, PlanError, load
from .sim import Settings, simulate

MAX_JSON = 2_000_000  # characters


def settings_from(d: Any) -> Settings:
    if d is None:
        return Settings()
    if not isinstance(d, dict):
        raise PlanError("settings must be an object")
    season = d.get("season", "summer")
    roof = d.get("roof", "dark")
    scenario = d.get("scenario", "normal")
    if season not in ("summer", "winter") or roof not in ("dark", "light") or scenario not in ("normal", "away"):
        raise PlanError("season, roof or scenario isn't one of the choices")

    def opt(key: str, lo: float, hi: float) -> float | None:
        v = d.get(key)
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise PlanError(f"{key} must be between {lo:g} and {hi:g}")
        return float(v)

    risk = opt("risk_hours", 1, 24)
    return Settings(
        season=season,
        roof=roof,
        scenario=scenario,
        setpoint=opt("setpoint", 45, 75),
        tmv_set=opt("tmv_set", 35, 55),
        risk_hours=risk if risk is not None else 4.0,
    )


def plan_from(source: Any) -> dict[str, Any]:
    """An example's name, or a plan as JSON text or a parsed object."""
    if isinstance(source, str) and source in examples.EXAMPLES:
        return examples.EXAMPLES[source]()
    if isinstance(source, str):
        if len(source) > MAX_JSON:
            raise PlanError("the plan is too large")
        try:
            source = json.loads(source)
        except (ValueError, RecursionError) as e:
            raise PlanError("the plan isn't valid JSON") from e
    if not isinstance(source, dict):
        raise PlanError("the plan must be a JSON object")
    return source


def drawing(b: Building) -> dict[str, Any]:
    """Everything the page needs to draw the building."""
    return {
        "name": b.name,
        "setpoint": b.setpoint,
        "size": b.size,
        "heater": b.heater_at,
        "meter": b.meter_at,
        "rooms": [{"name": r.name, "box": r.box} for r in b.rooms],
        "pipes": {
            pid: {
                "kind": p.kind,
                "zone": p.zone,
                "insulation": p.insulation,
                "dn": p.dn,
                "length": round(p.length, 2),
                "litres": round(p.volume * 1000, 3),
                "points": p.points,
            }
            for pid, p in b.pipes.items()
        },
        "tmvs": [{"id": t.id, "at": t.at, "set": t.set} for t in b.tmvs.values()],
        "outlets": {
            oid: {
                "name": o.name,
                "kind": o.kind,
                "at": o.at,
                "hot": o.hot,
                "cold": o.cold,
                "uses": sum(len(u.days) for u in o.uses),
            }
            for oid, o in b.outlets.items()
        },
    }


def check(source: Any, settings: Any = None) -> dict[str, Any]:
    data = plan_from(source)
    b = load(data)
    s = settings_from(settings)
    return {"building": drawing(b), "result": simulate(b, s)}


def plan(source: Any, settings: Any = None, progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    data = plan_from(source)
    load(data)
    s = settings_from(settings)
    return fixes.plan(data, s, progress)


def apply_fixes(source: Any, settings: Any, chosen: list[str]) -> dict[str, Any]:
    """The building and a full simulation with the chosen fixes made."""
    data = plan_from(source)
    known = {f.id for f in fixes.candidates(data)}
    if not isinstance(chosen, list) or not all(isinstance(c, str) and c in known for c in chosen):
        raise PlanError("unknown fix")
    d, extra = fixes.apply(data, chosen)
    b = load(d)
    return {"building": drawing(b), "result": simulate(b, settings_from(settings), extra)}


def call(request: str, progress: Callable[[int, int], None] | None = None) -> str:
    """The web worker's single entry point: {"op": ..., ...} in, {"ok": ..., ...} out (as JSON text)."""
    try:
        if not isinstance(request, str) or len(request) > MAX_JSON + 10_000:
            raise PlanError("the request is too large")
        req = json.loads(request)
        if not isinstance(req, dict):
            raise PlanError("bad request")
        op = req.get("op")
        if op == "check":
            out = check(req.get("plan"), req.get("settings"))
        elif op == "plan":
            out = plan(req.get("plan"), req.get("settings"), progress)
        elif op == "apply":
            out = apply_fixes(req.get("plan"), req.get("settings"), req.get("fixes", []))
        else:
            raise PlanError("unknown request")
        return json.dumps({"ok": True, **out}, separators=(",", ":"))
    except PlanError as e:
        return json.dumps({"ok": False, "error": str(e)})
    except (ValueError, KeyError, TypeError, RecursionError):
        return json.dumps({"ok": False, "error": "the plan couldn't be read"})
