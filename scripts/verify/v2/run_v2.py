"""Run the V2 matrix (scenarios of matrix_spec.py) through the chosen interfaces.

    python scripts/verify/v2/run_v2.py --protocol                    # write expectations.csv (before any run)
    python scripts/ops/gpulock_run.py v2 -- python scripts/verify/v2/run_v2.py --ifaces lib,mcp,cli [--only S01,..]
    python scripts/verify/v2/run_v2.py --ifaces gui --gui http://127.0.0.1:8767     # live GUI (takes the lock per job)
    python scripts/verify/v2/run_v2.py --tag probe --ifaces lib --only S01_targets  # pre-fix probe (own folder)

Writes results/verification/v2/observations/<tag>/<iface>__<scenario>.json (rows, every call with its full output,
the session log path). Sessions: results/verification/v2/sessions/[<tag>/]<iface>/<scenario>/ (never overwritten);
GUI sessions are written by the server under its --root.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2lib  # noqa: E402
from matrix_spec import S, SCENARIOS, rows_expected  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", action="store_true")
    ap.add_argument("--addendum", action="store_true", help="with --protocol: also write expectations_addendum.csv")
    ap.add_argument("--ifaces", default="lib")
    ap.add_argument("--only", default=None)
    ap.add_argument("--skip", default=None)
    ap.add_argument("--gui", default="http://127.0.0.1:8767")
    ap.add_argument("--tag", default="main")
    a = ap.parse_args(argv)
    if a.protocol:
        from matrix_spec import ADDENDUM
        rows = [x for x in rows_expected() if x["scenario"] not in ADDENDUM]
        add = [x for x in rows_expected() if x["scenario"] in ADDENDUM]
        p = v2lib.OUT / "expectations.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"{len(rows)} expected rows -> {p}")
        if not a.addendum:
            return 0
        p = v2lib.OUT / "expectations_addendum.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(add[0]))
            w.writeheader()
            w.writerows(add)
        print(f"{len(add)} addendum rows -> {p}")
        return 0
    if a.tag != "main":
        v2lib.SESS = v2lib.OUT / "sessions" / a.tag
    obs = v2lib.OUT / "observations" / a.tag
    obs.mkdir(parents=True, exist_ok=True)
    from matrix_spec import ADDENDUM
    only = a.only.split(",") if a.only else [s["id"] for s in S if s["id"] not in ADDENDUM]
    skip = set(a.skip.split(",")) if a.skip else set()
    import amm  # noqa: F401  (amm before torch)
    for iface in a.ifaces.split(","):
        def make(sdir, profile, iface=iface):
            if iface == "lib":
                return v2lib.LibDriver(sdir, profile)
            if iface == "mcp":
                return v2lib.McpDriver(sdir, profile)
            if iface == "gui":
                return v2lib.GuiDriver(a.gui, profile)
            if iface == "cli":
                return v2lib.CliDriver(sdir, profile)
            raise ValueError(iface)
        for sid in only:
            scn = SCENARIOS[sid]
            if sid in skip or iface not in scn["ifaces"]:
                continue
            print(f"== {iface} {sid}: {scn['title']}", flush=True)
            t = time.time()
            res = v2lib.run_scenario(scn, iface, make, log=lambda m: print(m, flush=True))
            res["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
            (obs / f"{iface}__{sid}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
            n_ok = sum(r["passed"] for r in res["rows"])
            print(f"   {n_ok}/{len(res['rows'])} passed, {time.time() - t:.1f} s, session {res['root']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
