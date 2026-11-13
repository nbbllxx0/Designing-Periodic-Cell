"""G2 classification after the fixes (certificate outcome from scripts/g2/rerun_v3.py).

Truth of each claim, from references at least as fine as the certificate's finest rung:
  static  phase means at n = 48, 64, 80, 96 over whatever phases exist at each n: five (0, 1/8, 1/4, 3/8, 1/2) at the
          certificate's rungs, three (0, 1/4, 1/2) or one (phase 0, TPMS) at n = 80 and 96 from the earlier re-run
          (`prior` rows). Means over three phases are noisier than over five (results/g2/NOTES.md).
          Candidates for the limit: fitted-order extrapolation from the three finest means (p in [0.25, 8], no cap),
          O(h) from the two finest means, and the finest mean. For E100, G and bulk the limit is also below every
          computed value (stiffness converges from above), so the bracket's upper end is capped by the smallest.
  gap     edges at n = 30, 40 (first pass) and 50 (scripts/g2/gap_ref_fine.py), fitted order and O(h) as above.
A claim is TRUE if it holds over the whole bracket, FALSE if it fails over the whole bracket, UNDETERMINED otherwise.
Also reports, for every accepted static bound, the bound against the bracket: past the limit side (a lower bound above
the lowest candidate; inside the bracket, so not decided) or past every candidate (sure unsound), with the excess
and the distance from the bound to the claim.
Output: results/g2/classification_v3.json and a table.
"""
import glob, json, os
from collections import Counter
import numpy as np
from scipy.optimize import brentq

import amm  # noqa: F401
from amm import certify

PH = ("0.0", "0.125", "0.25", "0.375", "0.5")
FROM_ABOVE = ("E100", "G", "bulk")


def order_fit(ns, vs):
    (n1, n2, n3), (v1, v2, v3) = ns[-3:], vs[-3:]
    d12, d23 = v2 - v1, v3 - v2
    if d12 == 0 or d23 == 0 or d12 * d23 < 0 or abs(d23) >= abs(d12):
        return None
    h1, h2, h3 = 1 / n1, 1 / n2, 1 / n3
    g = lambda p: (h2 ** p - h3 ** p) / (h1 ** p - h2 ** p) - d23 / d12
    try:
        p = brentq(g, 0.25, 8.0)
    except ValueError:
        return None
    return dict(p=p, f0=v3 + d23 * h3 ** p / (h2 ** p - h3 ** p))


def bracket(ns, vs):
    (n2, n3), (v2, v3) = ns[-2:], vs[-2:]
    cands = {"finest": v3, "O(h)": v3 + (v3 - v2) * (1 / n3) / (1 / n2 - 1 / n3)}
    fit = order_fit(ns, vs) if len(ns) >= 3 else None
    if fit:
        cands[f"p={fit['p']:.2f}"] = fit["f0"]
    return dict(lo=min(cands.values()), hi=max(cands.values()), cands=cands)


def verdict(ok_all, ok_any):
    return "true" if ok_all else ("false" if not ok_any else "undetermined")


rows_out = []
for f in sorted(glob.glob("results/g2/cells/*_m0.05.json")):
    d = json.load(open(f))
    spec, tg, h = d["spec"], d["targets"], certify.spec_hash(d["spec"])
    p3 = f"results/g2/rerun_v3/{h}.json"
    if not os.path.exists(p3):
        continue
    r3 = json.load(open(p3))
    if "static" not in r3:
        continue
    rows = {**r3.get("prior", {}), **r3["rows"]}
    ph_at = {n: [k for k in rows if k.startswith(f"{n}@") and rows[k].get("E100") is not None] for n in (48, 64, 80, 96)}
    ns = [n for n in (48, 64, 80, 96) if ph_at[n]]
    row = dict(kind=spec["kind"], params=spec["params"], claims={}, bound_check={}, ref_phases={n: len(ph_at[n]) for n in ns})
    for key, (q, kind) in certify.STATIC_KEYS.items():
        if key not in tg:
            continue
        means = [float(np.mean([rows[k][q] for k in ph_at[n]])) for n in ns]
        b = bracket(ns, means)
        if q in FROM_ABOVE:
            cap = min(v[q] for v in rows.values() if v.get(q) is not None)
            b["hi"] = min(b["hi"], cap)
            b["lo"] = min(b["lo"], b["hi"])
        t = tg[key]
        ok = (lambda x: x >= t) if kind == "min" else (lambda x: x <= t)
        row["claims"][key] = dict(target=t, bracket=[b["lo"], b["hi"]], cands=b["cands"],
                                  truth=verdict(ok(b["lo"]) and ok(b["hi"]), ok(b["lo"]) or ok(b["hi"])))
        conv = r3["static"]["convergence"].get(q)
        if conv and r3["static"]["passed"]:
            bound = conv["lower"] if kind == "min" else conv["upper"]
            ref = b["lo"] if kind == "min" else b["hi"]
            far = b["hi"] if kind == "min" else b["lo"]  # the bracket's other end
            row["bound_check"][key] = dict(bound=bound, limit_side=ref, rel_excess=(bound / ref - 1) * (1 if kind == "min" else -1),
                                           unsound=bool(bound > ref if kind == "min" else bound < ref),
                                           unsound_sure=bool(bound > far if kind == "min" else bound < far),
                                           claim_gap=abs(t / bound - 1))
    gap = tg.get("gap")
    if gap:
        raw = {int(n): e for n, e in d["gap_ref"]["raw"].items()}
        fp = f"results/g2/gap_ref_fine/{h}.json"
        if os.path.exists(fp) and json.load(open(fp)).get("version") == 2:
            raw.update({int(n): e for n, e in json.load(open(fp))["raw"].items() if int(n) >= 50})
        if any(e is None for e in raw.values()):
            row["claims"]["gap"] = dict(target=gap, truth="false", note="gap closes at a finer resolution")
        else:
            gn = sorted(raw)
            blo, bhi = bracket(gn, [raw[n][0] for n in gn]), bracket(gn, [raw[n][1] for n in gn])
            ok_all = gap["f_lo"] >= blo["hi"] and gap["f_hi"] <= bhi["lo"]
            ok_any = gap["f_lo"] >= blo["lo"] and gap["f_hi"] <= bhi["hi"]
            row["claims"]["gap"] = dict(target=gap, lower_edge=blo, upper_edge=bhi, truth=verdict(ok_all, ok_any))
    truths = [c["truth"] for c in row["claims"].values()]
    row["claim_truth"] = "false" if "false" in truths else ("undetermined" if "undetermined" in truths else "true")
    st_pass = r3["static"]["passed"]
    bl = r3.get("bloch")
    if gap and bl is None:
        continue  # Bloch block not run yet
    bl_pass = bl["passed"] if bl else True
    row.update(static_passed=st_pass, bloch_passed=bl_pass if bl else None, passed=bool(st_pass and bl_pass),
               static_used=r3["static"]["used"], static_fails=r3["static"]["checks_failed"],
               static_seconds=r3.get("static_seconds"), bloch_seconds=r3.get("bloch_seconds"))
    if bl:
        row["count_failures"] = {n: v["n_failures"] for n, v in bl.get("resolutions", {}).items()}
        row["safe_interval"] = (bl.get("convergence") or {}).get("safe_interval")
    if row["passed"]:
        row["cls"] = "accepted" + (" (claim FALSE: unsound)" if row["claim_truth"] == "false" else "")
    elif row["claim_truth"] == "false":
        row["cls"] = "correct refusal (claim false)"
    elif row["claim_truth"] == "undetermined":
        row["cls"] = "undetermined (reference not converged at this margin)"
    elif bl and not bl_pass:
        row["cls"] = ("false alarm (resolution)" if any(row["count_failures"].values()) else "false alarm (guard)")
    else:
        row["cls"] = "false alarm (static)"
    rows_out.append(row)

json.dump(rows_out, open("results/g2/classification_v3.json", "w"), indent=1, default=float)
print(len(rows_out), "cells", Counter(r["cls"] for r in rows_out))
uns = [(r["kind"], r["params"], k) for r in rows_out for k, v in r["bound_check"].items() if v["unsound"]]
print(f"bounds past the bracket's limit side (inside the bracket): {len(uns)}, worst excess "
      f"{max([v['rel_excess'] for r in rows_out for v in r['bound_check'].values() if v['unsound']] or [0]):+.4f}, "
      f"smallest distance to the claim {min([v['claim_gap'] for r in rows_out for v in r['bound_check'].values() if v['unsound']] or [1]):.3f}")
print("bounds past every limit candidate (sure unsound):",
      [(r["kind"], r["params"], k) for r in rows_out for k, v in r["bound_check"].items() if v["unsound_sure"]])
print("flagged:", uns)
for r in rows_out:
    if r["cls"] != "accepted":
        bad = {k: c["truth"] for k, c in r["claims"].items() if c["truth"] != "true"}
        print(f"{r['cls']:<52} {r['kind']:<16} {json.dumps(r['params']):<28} static {r['static_passed']} "
              f"bloch {r['bloch_passed']} {bad} {r['static_fails']}")
