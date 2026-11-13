"""V10 set 1: the stratified sample of frozen E4 sessions (rule and seed in results/verification/v10/NOTES.md 1.2).

    python scripts/verify/v10/select_e4.py

Strata: arm (D, B, C) x outcome (released = decision "release", refused = decision "refuse", other = anything
else), from results/bench/e4/scores.json (frozen scoring output; read only). 5 sessions per arm. Within an arm:
1 per non-empty stratum, the rest by largest remainder in proportion to stratum size (ties: released, refused,
other). Draw: random.Random(SEED).sample over the sorted job names of each stratum, strata visited in the order
arm D, B, C and outcome released, refused, other. Writes results/verification/v10/e4_sample.json and e4_sample.txt
(log paths).
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v10"
SEED = 20261108
PER_ARM = 5
ARMS = ("D", "B", "C")
OUTCOMES = ("released", "refused", "other")


def outcome(x):
    return {"release": "released", "refuse": "refused"}.get(x.get("decision"), "other")


def allocate(sizes: dict, n: int) -> dict:
    nonempty = [o for o in OUTCOMES if sizes.get(o, 0) > 0]
    alloc = {o: 0 for o in OUTCOMES}
    for o in nonempty:
        alloc[o] = 1
    rest = n - len(nonempty)
    tot = sum(sizes[o] for o in nonempty)
    quota = {o: rest * sizes[o] / tot for o in nonempty}
    for o in nonempty:
        alloc[o] += math.floor(quota[o])
    left = n - sum(alloc.values())
    for o in sorted(nonempty, key=lambda o: (-(quota[o] - math.floor(quota[o])), OUTCOMES.index(o)))[:left]:
        alloc[o] += 1
    for o in nonempty:
        alloc[o] = min(alloc[o], sizes[o])
    return alloc


def main():
    scores = json.loads((ROOT / "results/bench/e4/scores.json").read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    strata, sample = {}, []
    for arm in ARMS:
        jobs = {o: sorted(x["job"] for x in scores if x["arm"] == arm and outcome(x) == o) for o in OUTCOMES}
        sizes = {o: len(v) for o, v in jobs.items()}
        alloc = allocate(sizes, PER_ARM)
        for o in OUTCOMES:
            pick = sorted(rng.sample(jobs[o], alloc[o])) if alloc[o] else []
            strata[f"{arm}/{o}"] = dict(size=sizes[o], n=alloc[o], picked=pick)
            for j in pick:
                x = next(s for s in scores if s["job"] == j)
                sample.append(dict(job=j, arm=arm, stratum=o, brief=x["brief"], decision=x["decision"],
                                   verdict=x["verdict"], score_outcome=x["outcome"], n_calls=x["n_calls"],
                                   n_certify=x["n_certify"], n_search=x["n_search"],
                                   logged_tool_seconds=x["tool_seconds"],
                                   log=f"results/bench/e4/jobs/{j}/session/session.jsonl"))
    res = dict(seed=SEED, per_arm=PER_ARM, rule=__doc__.split("\n\n")[1].strip(), strata=strata, sample=sample,
               n=len(sample), sum_logged_tool_seconds=round(sum(s["logged_tool_seconds"] or 0 for s in sample), 1))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e4_sample.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    (OUT / "e4_sample.txt").write_text("\n".join(s["log"] for s in sample) + "\n", encoding="utf-8")
    for k, v in strata.items():
        print(k, v["size"], v["n"], v["picked"])
    print("n", len(sample), "sum logged tool seconds", res["sum_logged_tool_seconds"])


if __name__ == "__main__":
    main()
