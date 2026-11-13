"""V11 (audit round 1, 2026-11-08): harness sensitivity of the E4 primary contrast (no new runs, no LLM calls).

Amendment A1 changed the harness (scripts/bench/e4.py) after 29 of the 234 retained jobs had finished. This repeats
the pre-registered primary analysis (paired C - B per-specification correctness on witnessed and proven specs, same
code as e4.py analyze) on two subsets of the scored records:
  amended_only: jobs whose run.json carries the amended harness identity;
  both_arms_same_harness: specifications whose B and C jobs all ran under one harness (either).
Writes results/bench/e4/sensitivity_harness_v11.json.
"""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
E4 = ROOT / "results/bench/e4"
recs = json.loads((E4 / "scores.json").read_text(encoding="utf-8"))
harness = {}
for d in (E4 / "jobs").iterdir():
    f = d / "run.json"
    if f.exists():
        harness[d.name] = json.loads(f.read_text(encoding="utf-8")).get("harness")
need = {j["job"] for j in json.loads((E4 / "jobs.json").read_text(encoding="utf-8"))["jobs"]} if isinstance(
    json.loads((E4 / "jobs.json").read_text(encoding="utf-8")), dict) and "jobs" in json.loads(
    (E4 / "jobs.json").read_text(encoding="utf-8")) else None
conf = [r for r in recs if r["partition"] == "confirmatory" and r["provider"] in ("codex", "none")
        and r["job"] in harness]


def per_spec(rs, arm, level):
    out = {}
    for r in rs:
        if r["arm"] != arm or r["truth_level"] not in level:
            continue
        out.setdefault(r["spec_key"], []).append(float(r["correct"]))
    return {k: float(np.mean(v)) for k, v in out.items()}


def paired(rs, keys_filter=None, n_boot=10000, seed=1):
    lv = ("witnessed", "proven")
    pa, pb = per_spec(rs, "C", lv), per_spec(rs, "B", lv)
    keys = sorted(set(pa) & set(pb))
    if keys_filter is not None:
        keys = [k for k in keys if k in keys_filter]
    d = np.array([pa[k] - pb[k] for k in keys])
    rng = np.random.default_rng(seed)
    boots = d[rng.integers(0, len(d), size=(n_boot, len(d)))].mean(axis=1)
    flips = rng.choice([-1.0, 1.0], size=(100_000, len(d)))
    perm = np.abs((flips * d).mean(axis=1))
    p = float((np.sum(perm >= abs(d.mean()) - 1e-12) + 1) / (len(perm) + 1))
    return dict(n_specs=len(keys), mean_C=float(np.mean([pa[k] for k in keys])),
                mean_B=float(np.mean([pb[k] for k in keys])), diff=float(d.mean()),
                ci95=[float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
                specs_C_better=int((d > 0).sum()), specs_B_better=int((d < 0).sum()), p=p)


AMENDED = "34193563196998ce"
by_arm = {}
for r in conf:
    by_arm.setdefault((r["arm"], harness[r["job"]] == AMENDED), 0)
    by_arm[(r["arm"], harness[r["job"]] == AMENDED)] += 1
full = paired(conf)
amended_only = paired([r for r in conf if harness[r["job"]] == AMENDED])
spec_h = {}
for r in conf:
    if r["arm"] in ("B", "C"):
        spec_h.setdefault(r["spec_key"], set()).add(harness[r["job"]])
same = {k for k, v in spec_h.items() if len(v) == 1}
same_h = paired(conf, keys_filter=same)
out = dict(jobs_by_arm_and_harness={f"{a}|{'amended' if h else 'original'}": n for (a, h), n in sorted(by_arm.items())},
           full=full, amended_only=amended_only, both_arms_same_harness=same_h,
           note="primary contrast C - B, per-spec correctness over witnessed and proven specs; paired sign-flip "
                "permutation (100,000 draws) and spec bootstrap, as in scripts/bench/e4.py analyze")
(E4 / "sensitivity_harness_v11.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
