"""Week 4: Codex probe on the 5 probe briefs (bench/probe/P*.json), arm C, then LLM-free replay of each session.

Usage: run_probe.py [P3 P4 ...] [--profile C] [--no-replay]  -> results/probe/<profile>/<brief>/ and summary.json
Each brief: one `codex exec` session (gpt-6.1-sol, effort high, subscription login, amm MCP server only), its tool
log session/session.jsonl, the final message, token usage and wall time; then amm.tools.replay on the log.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from amm import bench, tools  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
profile = "B" if "--profile=B" in sys.argv or ("--profile" in sys.argv and sys.argv[sys.argv.index("--profile") + 1] == "B") else "C"
args = [a for a in args if a not in ("B", "C")]
ids = args or ["P3", "P4", "P5", "P1", "P2"]
out_root = ROOT / "results" / "probe" / profile
out_root.mkdir(parents=True, exist_ok=True)
summary_path = out_root / "summary.json"
summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}

for bid in ids:
    brief_path = ROOT / "bench" / "probe" / f"{bid}.json"
    out = out_root / bid
    if (out / "run.json").exists():
        print(bid, "already run", flush=True)
        rec = json.loads((out / "run.json").read_text())
    else:
        print(bid, "running", time.strftime("%H:%M:%S"), flush=True)
        rec = bench.run_brief(brief_path, out, profile=profile)
    log = out / "session" / "session.jsonl"
    calls = [r for r in tools.read_log(log) if r.get("type") == "call"] if log.exists() else []
    sub = next((r["result"]["submitted"] for r in calls if r["tool"] == "submit" and r["ok"]), None)
    row = dict(brief=bid, returncode=rec["returncode"], wall_s=rec["wall_s"], usage=rec["usage"],
               n_calls=len(calls), n_failed_calls=sum(not r["ok"] for r in calls),
               tools_used=sorted({r["tool"] for r in calls}), submission=sub,
               expected=bench.load_brief(brief_path)["expected"], final=rec["final"][:600])
    if "--no-replay" not in sys.argv and log.exists():
        t0 = time.perf_counter()
        rep = tools.replay(log, root=out / "replay")
        row["replay"] = dict(exact=rep["exact"], same_code=rep["same_code"], n_compared=rep["n_compared"],
                             mismatches=rep["mismatches"][:5],
                             seconds=round(time.perf_counter() - t0, 1))
    summary[bid] = row
    summary_path.write_text(json.dumps(summary, indent=1, default=float), encoding="utf-8")
    print(json.dumps(dict(brief=bid, rc=row["returncode"], calls=row["n_calls"], failed=row["n_failed_calls"],
                          submission=sub and {k: sub.get(k) for k in ("decision", "verdict", "design")},
                          replay=row.get("replay", {}).get("exact"), wall=row["wall_s"],
                          tokens=rec["usage"]), default=float), flush=True)
