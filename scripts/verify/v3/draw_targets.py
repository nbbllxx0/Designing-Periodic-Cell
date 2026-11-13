"""V3 target draw (rule: results/verification/v3/NOTES.md section 2). Writes results/verification/v3/targets.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "bench"))
import scoring  # noqa: E402  (spec_key only)

SEED = 20261108
N_PRIMARY = 20
NU = {"316L": 0.3, "Ti6Al4V": 0.342, "PA12": 0.39}
OUT = ROOT / "results" / "verification" / "v3" / "targets.json"


def pool():
    jobs = json.loads((ROOT / "results" / "bench" / "e4" / "jobs.json").read_text(encoding="utf-8"))
    part = {j["brief"]: j["partition"] for j in jobs["jobs"]}
    specs = {}
    for p in sorted((ROOT / "bench" / "v1" / "briefs").glob("*.json")):
        b = json.loads(p.read_text(encoding="utf-8"))
        if part.get(b["id"]) != "confirmatory" or b["truth"].get("certificate") != "certified":
            continue
        specs.setdefault(scoring.spec_key(b), []).append(b)
    out = []
    for k, bs in specs.items():
        main = sorted([x for x in bs if not x["cls"].startswith("ambiguous")] or bs, key=lambda x: x["id"])[0]
        t = main["intended"]["targets"]
        ttype = "combined" if main["cls"] == "feasible_combined" else ("gap" if "gap" in t else "static")
        out.append(dict(target_id=main["id"], spec_key=k, briefs=sorted(x["id"] for x in bs),
                        material=main["intended"]["material"], nu=NU[main["intended"]["material"]],
                        targets=main["truth"]["normalized"], target_type=ttype,
                        witness_family=main["truth"]["witness"]["family"], witness=main["truth"]["witness"],
                        difficulty=main["truth"]["difficulty"], intended=main["intended"]))
    return sorted(out, key=lambda x: x["target_id"])


def main():
    rng = np.random.default_rng(SEED)
    P = pool()
    assert len(P) == 42, len(P)
    strata = {}
    for x in P:
        strata.setdefault((x["witness_family"], x["target_type"]), []).append(x)
    keys = sorted(strata)
    q = {k: N_PRIMARY * len(strata[k]) / len(P) for k in keys}
    quota = {k: max(1, int(np.floor(q[k]))) for k in keys}
    left = N_PRIMARY - sum(quota.values())
    rem = {k: q[k] - np.floor(q[k]) for k in keys}
    # largest remainders; ties broken by one seeded permutation of the strata
    perm = {k: i for i, k in enumerate([keys[i] for i in rng.permutation(len(keys))])}
    for k in sorted(keys, key=lambda k: (-round(rem[k], 12), perm[k]))[:left]:
        quota[k] += 1
    assert sum(quota.values()) == N_PRIMARY
    drawn = []
    for k in keys:
        s = sorted(strata[k], key=lambda x: x["target_id"])
        idx = rng.choice(len(s), size=quota[k], replace=False)
        drawn += [s[i] for i in sorted(idx)]
    order = rng.permutation(len(drawn))
    primary = [drawn[i] for i in order]
    for i, x in enumerate(primary):
        x["order"], x["set"] = i, "primary"
    ids = {x["target_id"] for x in primary}
    calib = []
    for nu in (0.342, 0.39):
        s = sorted([x for x in P if x["target_id"] not in ids and x["nu"] == nu], key=lambda x: x["target_id"])
        idx = rng.choice(len(s), size=2, replace=False)
        calib += [s[i] for i in sorted(idx)]
    for i, x in enumerate(calib):
        x["order"], x["set"] = N_PRIMARY + i, "calibration"
    out = dict(seed=SEED, rule="results/verification/v3/NOTES.md section 2", pool_size=len(P),
               strata={f"{a}/{b}": len(strata[(a, b)]) for a, b in keys},
               quota={f"{a}/{b}": quota[(a, b)] for a, b in keys},
               targets=primary + calib)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out["quota"]))
    for x in primary + calib:
        print(x["order"], x["set"], x["target_id"], x["material"], x["witness_family"], x["target_type"],
              x["difficulty"], sorted(x["targets"]))


if __name__ == "__main__":
    main()
