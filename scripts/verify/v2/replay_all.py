"""V2 deliverable 8: replay every session log V2 wrote (amm.tools.replay, no LLM), under the solver lock.

    python scripts/ops/gpulock_run.py v2 -- python scripts/verify/v2/replay_all.py [--tag main|probe|all]

Writes results/verification/v2/replays.json and replays.csv (one row per log: interface, scenario, exact, calls
compared, mismatches, identity aliasing, seconds).
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


def logs(tag):
    base = v2lib.SESS
    out = []
    for p in sorted(base.rglob("session.jsonl")):
        rel = p.relative_to(base).parts
        is_probe = rel[0] == "probe"
        if tag == "main" and is_probe or tag == "probe" and not is_probe:
            continue
        out.append(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="all", choices=["main", "probe", "all"])
    a = ap.parse_args(argv)
    import amm  # noqa: F401
    from amm import tools
    rows, full = [], []
    for p in logs(a.tag):
        rel = p.relative_to(v2lib.SESS).parts
        iface = rel[1] if rel[0] == "probe" else rel[0]
        t = time.time()
        recs = tools.read_log(p)
        n_calls = sum(1 for r in recs if r.get("type") == "call")
        try:
            rep = tools.replay(p)
            err = None
        except Exception as ex:  # noqa: BLE001
            rep, err = None, f"{type(ex).__name__}: {ex}"
        dt = round(time.time() - t, 1)
        tools_used = sorted({r["tool"] for r in recs if r.get("type") == "call"})
        row = dict(log=str(p.relative_to(v2lib.ROOT)).replace("\\", "/"), tag="probe" if rel[0] == "probe" else "main",
                   interface={"gui_edge": "gui-edge"}.get(iface, iface), n_calls=n_calls,
                   n_compared=rep["n_compared"] if rep else None, exact=bool(rep and rep["exact"]),
                   mismatches=len(rep["mismatches"]) if rep else None,
                   mismatch_tools=";".join(f"{m['seq']}:{m['tool']}:{m['field']}" for m in rep["mismatches"]) if rep else err,
                   code_aliased=rep["identity"]["code_aliased"] if rep else None,
                   checker_aliased=rep["identity"]["checker_aliased"] if rep else None,
                   certify_calls=sum(1 for r in recs if r.get("type") == "call" and r["tool"] == "certify" and r["ok"]),
                   export_calls=sum(1 for r in recs if r.get("type") == "call" and r["tool"] == "export" and r["ok"]),
                   tools=" ".join(tools_used), seconds=dt)
        rows.append(row)
        full.append(dict(row, report=rep, error=err))
        print(f"{row['log']}: exact {row['exact']} ({row['n_compared']}/{n_calls}) {row['mismatch_tools'] or ''} "
              f"[{dt} s]", flush=True)
    out = v2lib.OUT / ("replays.json" if a.tag in ("all", "main") else f"replays_{a.tag}.json")
    out.write_text(json.dumps(full, indent=1, default=str), encoding="utf-8")
    with open(out.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n = sum(r["exact"] for r in rows)
    print(f"{n}/{len(rows)} logs exact -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
