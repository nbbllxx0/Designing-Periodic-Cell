"""Week 5 pilot / E4 runs: one Codex session per (brief, arm), then scoring.

    run_arms.py run   [--arms B,C] [--ids S01,G02 | --pilot] [--parallel 2] [--tag pilot]
    run_arms.py score [--arms B,C] [--tag pilot] [--no-certify]

Sessions: results/bench/<tag>/<arm>/<brief>/ (prompt, codex events, session log, run.json). A finished session
(run.json present) is never re-run. Scores: results/bench/<tag>/scores.json and summary.json.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from amm import bench, tools  # noqa: E402
import scoring  # noqa: E402

BRIEFS = ROOT / "bench" / "v1" / "briefs"


def opt(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else default


def ids_arg() -> list[str]:
    man = json.loads((ROOT / "bench" / "v1" / "manifest.json").read_text(encoding="utf-8"))
    if "--pilot" in sys.argv:
        return [i for i in man["pilot"] if i in man["ids"]]
    if opt("--ids"):
        return opt("--ids").split(",")
    return man["ids"]


def run_one(bid: str, arm: str, out_root: Path) -> dict:
    out = out_root / arm / bid
    if (out / "run.json").exists():
        return json.loads((out / "run.json").read_text(encoding="utf-8"))
    print(f"{time.strftime('%H:%M:%S')} start {arm} {bid}", flush=True)
    rec = bench.run_brief(BRIEFS / f"{bid}.json", out, profile=arm)
    print(f"{time.strftime('%H:%M:%S')} done  {arm} {bid} rc={rec['returncode']} wall={rec['wall_s']}s", flush=True)
    return rec


def run():
    arms = opt("--arms", "B,C").split(",")
    out_root = ROOT / "results" / "bench" / opt("--tag", "pilot")
    jobs = [(b, a) for b in ids_arg() for a in arms]  # interleave arms so a stop leaves balanced pairs
    with ThreadPoolExecutor(int(opt("--parallel", "2"))) as ex:
        list(ex.map(lambda j: run_one(j[0], j[1], out_root), jobs))
    print("all sessions done; code", tools.code_hash(), flush=True)


def score():
    arms = opt("--arms", "B,C").split(",")
    tag = opt("--tag", "pilot")
    out_root = ROOT / "results" / "bench" / tag
    recs = []
    for arm in arms:
        for d in sorted((out_root / arm).glob("*")):
            if not (d / "session" / "session.jsonl").exists():
                continue
            brief = json.loads((BRIEFS / f"{d.name}.json").read_text(encoding="utf-8"))
            r = scoring.score_session(brief, d, certify_releases="--no-certify" not in sys.argv,
                                      legacy_ok=True)  # development runs only: labelled checker="legacy"
            r["arm"] = arm
            r["expected"] = brief["expected"]["decision"]
            recs.append(r)
            print(arm, d.name, r["outcome"], r["decision"], r.get("verdict") or "",
                  (r["release_check"] or {}).get("verdict", ""), flush=True)
    (out_root / "scores.json").write_text(json.dumps(recs, indent=1, default=float), encoding="utf-8")
    summ = {arm: scoring.summarize([r for r in recs if r["arm"] == arm]) for arm in arms}
    (out_root / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    {"run": run, "score": score}[sys.argv[1]]()
