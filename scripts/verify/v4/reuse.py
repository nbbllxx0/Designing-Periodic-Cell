"""V4 items 3 and 5 (and the reused part of item 2): certificate times, workflow times and agent-session tool
latencies from logs that already exist. Nothing is recomputed.

    python scripts/verify/v4/reuse.py

Sources (read only):
- results/verification/v3/certs/*.json (85 unique certificates; full certificate with timing blocks), targets.json,
  runs.csv (workflow = search + certificate seconds per target x method);
- results/verification/v1b/*_amm.json (6 certificates, as-built on);
- results/bench/e4/jobs/*/session/certificates/*.json (82 certificates written by agent sessions) and
  results/bench/e4/jobs/*/session/session.jsonl (dt_s of every tool call);
- results/verification/v4/latency_session/certificates/*.json (the 3 fresh V4 certificates), if present.
Writes raw/cert_times_rows.csv, raw/workflow_rows.csv, raw/e4_tool_calls.csv (row level). The summary tables are
written by tables.py.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

R = common.ROOT / "results"
V3, V1B, E4 = R / "verification" / "v3", R / "verification" / "v1b", R / "bench" / "e4"


def ttype(targets: dict) -> str:
    gap = "gap" in targets
    static = any(k != "gap" for k in targets)
    return "combined" if gap and static else ("gap" if gap else "static")


def cert_row(c: dict, **kw) -> dict:
    tm = c.get("timing") or {}
    st = (c.get("blocks") or {}).get("static") or {}
    return dict(kw, family=c["spec"]["family"], kind=c["spec"]["kind"], spec_hash=c.get("spec_hash"),
                target_type=ttype(c["targets"]), verdict=c.get("verdict"), checker=c.get("checker"),
                total_s=c.get("seconds"), static_s=tm.get("static"), bloch_s=tm.get("bloch"),
                as_built_s=tm.get("as_built"), static_rung="-".join(map(str, st.get("used") or [])),
                static_rungs_tried=len(st.get("ladder") or []))


def certs() -> list[dict]:
    rows = []
    for p in sorted((V3 / "certs").glob("*.json")):
        if p.name.endswith(".summary.json"):
            continue
        c = json.loads(p.read_text(encoding="utf-8"))
        rows.append(cert_row(c, source="V3", cert_id=p.stem, target_id=p.stem.split("_")[0], as_built_on=False,
                             mkl_threads=16, load="one certificate process at a time (V3 NOTES section 5)"))
    for p in sorted(V1B.glob("*_amm.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        rows.append(cert_row(c, source="V1b", cert_id=p.stem, target_id=p.stem[:-4], as_built_on=True,
                             mkl_threads=12, load="concurrent jobs, up to 24-28 threads at times (V1b NOTES)"))
    for p in sorted(E4.glob("jobs/*/session/certificates/*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        job = p.parts[-4]
        rows.append(cert_row(c, source="E4", cert_id=f"{job}/{p.stem}", target_id=job, as_built_on=True,
                             mkl_threads=16, load="agent session; jobs serialized by the e4 runner and solver lock"))
    fresh = common.OUT / "latency_session" / "certificates"
    for p in sorted(fresh.glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        rows.append(cert_row(c, source="V4 fresh", cert_id=p.stem, target_id="", as_built_on=True, mkl_threads=16,
                             load="alone (V4 latency run, GPU lock)"))
    return rows


def workflow() -> list[dict]:
    rows = []
    with open(V3 / "runs.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s, c, w = float(r["search_seconds"]), float(r["cert_seconds"] or 0), float(r["workflow_seconds"])
            rows.append(dict(target_id=r["target_id"], set=r["set"], target_type=r["target_type"], nu=r["nu"],
                             method=r["method"], method_name=r["method_name"], evals_spent=r["evals_spent"],
                             search_s=s, cert_s=c, workflow_s=w, check_sum=round(abs(s + c - w), 3),
                             cert_calls=r["cert_calls"], cert_verdict=r["cert_verdict"],
                             certified=r["certified"] == "True", cert_shared_with=r["cert_shared_with"],
                             throughput_evals_per_s=r["throughput_evals_per_s"]))
    return rows


def e4_calls() -> list[dict]:
    rows = []
    for p in sorted(E4.glob("jobs/*/session/session.jsonl")):
        job = p.parts[-3]
        run = json.loads((p.parent.parent / "run.json").read_text(encoding="utf-8")) \
            if (p.parent.parent / "run.json").exists() else {}
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("type") != "call":
                continue
            res = r.get("result") or {}
            rows.append(dict(job=job, arm=run.get("arm"), code=run.get("code"), checker=run.get("checker"),
                             tool=r["tool"], ok=r["ok"], dt_s=r["dt_s"], actor=r.get("actor"),
                             n_designs=len((r.get("args") or {}).get("designs") or []) or None,
                             budget=(r.get("args") or {}).get("budget", 32 if r["tool"] == "search" else None)))
    return rows


def main():
    c = certs()
    common.write_csv(common.RAW / "cert_times_rows.csv", c)
    w = workflow()
    common.write_csv(common.RAW / "workflow_rows.csv", w)
    e = e4_calls()
    common.write_csv(common.RAW / "e4_tool_calls.csv", e)
    from collections import Counter
    print("certs", Counter(r["source"] for r in c), "checkers", Counter((r["source"], r["checker"]) for r in c))
    print("workflow rows", len(w), "max |search+cert-workflow|", max(r["check_sum"] for r in w))
    print("e4 calls", len(e), Counter(r["tool"] for r in e).most_common())


if __name__ == "__main__":
    main()
