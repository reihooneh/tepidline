"""Command line: python -m tepidline check|plan|verify|example ..."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import api, examples, verify
from .model import PlanError

MAX_FILE = 2_000_000


def _read(source: str) -> str:
    if source in examples.EXAMPLES:
        return source
    if not os.path.isfile(source):
        raise PlanError(f"{source} isn't a file or an example ({', '.join(examples.EXAMPLES)})")
    if os.path.getsize(source) > MAX_FILE:
        raise PlanError("the plan file is larger than 2 MB")
    with open(source, encoding="utf-8") as f:
        return f.read()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tepidline", description="Finds water that sits warm in a building's pipes.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "plan"):
        p = sub.add_parser(name)
        p.add_argument("plan", help="a plan JSON file, or an example: " + ", ".join(examples.EXAMPLES))
        p.add_argument("--season", choices=["summer", "winter"], default="summer")
        p.add_argument("--roof", choices=["dark", "light"], default="dark")
        p.add_argument("--scenario", choices=["normal", "away"], default="normal")
        p.add_argument("--json", action="store_true")
        if name == "plan":
            p.add_argument("--budget", type=float, default=2000)
    e = sub.add_parser("example")
    e.add_argument("name", choices=list(examples.EXAMPLES))
    sub.add_parser("verify")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "example":
            print(json.dumps(examples.EXAMPLES[a.name](), indent=1))
            return 0
        if a.cmd == "verify":
            report = verify.run()
            print(json.dumps(report, indent=1))
            return 0 if all(c["pass"] for c in report["checks"]) else 1
        settings = {"season": a.season, "roof": a.roof, "scenario": a.scenario}
        src = _read(a.plan)
        if a.cmd == "check":
            out = api.check(src, settings)
            if a.json:
                print(json.dumps(out, separators=(",", ":")))
            else:
                _report(out)
        else:
            res = api.plan(src, settings)
            if a.json:
                print(json.dumps(res, separators=(",", ":")))
            else:
                _plan_report(res, a.budget)
        return 0
    except PlanError as err:
        print(f"tepidline: {err}", file=sys.stderr)
        return 2


def _report(out: dict) -> None:  # type: ignore[type-arg]
    b, r = out["building"], out["result"]
    print(f"{b['name']}: {len(b['pipes'])} pipes, {len(b['outlets'])} outlets")
    print(f"Weighted risky litres a week: {r['score']:.1f}\n")
    print(f"{'Outlet':<22}{'risky L/wk':>11}{'worst warm h':>14}{'L till hot':>12}")
    for oid, o in sorted(r["outlets"].items(), key=lambda kv: -kv[1]["risky_litres"] * kv[1]["weight"]):
        print(f"{b['outlets'][oid]['name']:<22}{o['risky_litres']:>11.1f}{o['worst_hours']:>14.1f}{o['wait_litres']:>12.1f}")
    print("\nWarmest pipes (warm hours a day):")
    for pid, p in sorted(r["pipes"].items(), key=lambda kv: -kv[1]["band_hours"])[:6]:
        info = b["pipes"][pid]
        print(f"  {pid:<14}{info['kind']:<9}{info['zone']:<11}{p['band_hours']:>5.1f} h")


def _plan_report(res: dict, budget: float) -> None:  # type: ignore[type-arg]
    names = {f["id"]: f for f in res["fixes"]}
    print(f"Baseline: {res['baseline']['score']:.1f} weighted risky litres a week; {len(res['combos'])} combinations tried.\n")
    print("Best for each budget:")
    for row in res["frontier"]:
        fx = ", ".join(names[f]["title"] for f in row["fixes"]) or "nothing"
        print(f"  ${row['cost']:>6,.0f}  {row['score']:>6.1f}  {fx}")


if __name__ == "__main__":
    sys.exit(main())
