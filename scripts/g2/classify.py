"""G2 classification: is each refusal a false alarm?

A refusal is a false alarm only if the claim is true in the converged limit. The first-pass references (static
O(h) from n = 64, 80; gap O(h) from n = 30, 40) are themselves estimates, so the limit is bracketed here from more
resolutions:
  gap     n = 30, 40 (first pass) and 50, 60 (gap_ref_fine.py), at the same k set;
  static  n = 32, 48, 64, 80 (and 96 where the first re-run escalated); the static outcome is from the
          phase-guarded block (static_rerun_phase.py), whose n = 80 phase solves also bound the limit from above
          (stiffness converges from above): the bracket's upper end is capped by the smallest of them.
Candidates for the limit: O(h) extrapolation from the two finest resolutions, and a fitted-order extrapolation
f = f0 + C h^p from the three finest (p solved from the ratio of successive changes; only for a monotone sequence
with shrinking steps, p in [0.25, 4]). The limit is bracketed by the candidates and the finest computed value:
[min, max]. A claim is TRUE if it holds at every point of the bracket, FALSE if it fails at every point, and
UNDETERMINED otherwise (the references cannot decide it at this margin).

Refusal classes:
  claim false                 correct refusal
  undetermined                the claim's truth is not settled by the references; not counted as a false alarm
  false alarm (resolution)    claim true, but the discrete model at the certificate's resolutions violates it
  false alarm (guard)         claim true, counts pass, the convergence guard refuses
  false alarm (static)        claim true, the static block refuses
Outputs results/g2/classification.json and prints a table.
"""
import glob, json, os
import numpy as np
from scipy.optimize import brentq

import amm  # noqa: F401
from amm import certify


def order_fit(ns, vs):
    """Fitted-order extrapolation from the three finest points, or None."""
    (n1, n2, n3), (v1, v2, v3) = ns[-3:], vs[-3:]
    d12, d23 = v2 - v1, v3 - v2
    if d12 == 0 or d23 == 0 or d12 * d23 < 0 or abs(d23) >= abs(d12):
        return None
    h1, h2, h3 = 1 / n1, 1 / n2, 1 / n3
    g = lambda p: (h2 ** p - h3 ** p) / (h1 ** p - h2 ** p) - d23 / d12
    try:
        p = brentq(g, 0.25, 4.0)
    except ValueError:
        return None
    # f = f0 + C h^p  =>  d23 = C (h3^p - h2^p),  f0 = v3 - C h3^p = v3 + d23 h3^p / (h2^p - h3^p)
    # (a sign error here, fixed 2026-11-04, put the fitted candidate on the wrong side of the finest value)
    return dict(p=p, f0=v3 + d23 * h3 ** p / (h2 ** p - h3 ** p))


def bracket(ns, vs):
    (n2, n3), (v2, v3) = ns[-2:], vs[-2:]
    cands = {"finest": v3, "O(h)": v3 + (v3 - v2) * (1 / n3) / (1 / n2 - 1 / n3)}
    fit = order_fit(ns, vs) if len(ns) >= 3 else None
    if fit:
        cands[f"p={fit['p']:.2f}"] = fit["f0"]
    return dict(lo=min(cands.values()), hi=max(cands.values()), cands=cands, values=dict(zip(ns, vs)))


def verdict(ok_all, ok_any):
    return "true" if ok_all else ("false" if not ok_any else "undetermined")


rerun = {certify.spec_hash(r["spec"]): r for r in json.load(open("results/g2/static_rerun.json"))}
phase = {}
for p in glob.glob("results/g2/static_rerun_phase/*.json"):  # per-cell files (the run may still be going)
    r = json.load(open(p))
    phase[certify.spec_hash(r["spec"])] = r
rows = []
for f in sorted(glob.glob("results/g2/cells/*_m0.05.json")):
    d = json.load(open(f))
    spec, h = d["spec"], certify.spec_hash(d["spec"])
    tg, s, sr = d["targets"], d["cert"]["static"], d["static_ref"]
    vals = {int(n): v for n, v in s["values"].items()}
    vals.update({int(n): v for n, v in sr["raw"].items()})
    rr = rerun.get(h)
    if rr and "ref96" in rr:
        vals[96] = rr["ref96"]
    ns = sorted(n for n in vals if vals[n].get("E100") is not None)
    row = dict(kind=spec["kind"], params=spec["params"], first_pass=d["cert"]["passed"])
    claims = {}
    for key, (q, kind) in certify.STATIC_KEYS.items():
        if key not in tg:
            continue
        b = bracket(ns, [vals[n][q] for n in ns])
        ph = phase.get(h)
        if ph and q in ph.get("finest_min", {}):  # converges from above: the limit is below every finest value
            b["hi"] = min(b["hi"], ph["finest_min"][q])
            b["lo"] = min(b["lo"], b["hi"])
        t = tg[key]
        ok = (lambda x: x >= t) if kind == "min" else (lambda x: x <= t)
        claims[key] = dict(target=t, bracket=[b["lo"], b["hi"]], cands=b["cands"],
                           truth=verdict(ok(b["lo"]) and ok(b["hi"]), ok(b["lo"]) or ok(b["hi"])))
    gap = tg.get("gap")
    if gap:
        fine_p = f"results/g2/gap_ref_fine/{h}.json"
        raw = {int(n): e for n, e in d["gap_ref"]["raw"].items()}
        if os.path.exists(fine_p):
            fine = json.load(open(fine_p))
            if fine.get("version") == 2:
                raw.update({int(n): e for n, e in fine["raw"].items() if int(n) >= 50})
        if any(e is None for e in raw.values()):
            claims["gap"] = dict(target=gap, truth="false", note="gap closes at a finer resolution",
                                 raw={n: e for n, e in raw.items()})
        else:
            gn = sorted(raw)
            blo = bracket(gn, [raw[n][0] for n in gn])
            bhi = bracket(gn, [raw[n][1] for n in gn])
            # gap claim true if f_lo >= every candidate lower edge and f_hi <= every candidate upper edge
            ok_all = gap["f_lo"] >= blo["hi"] and gap["f_hi"] <= bhi["lo"]
            ok_any = gap["f_lo"] >= blo["lo"] and gap["f_hi"] <= bhi["hi"]
            claims["gap"] = dict(target=gap, lower_edge=blo, upper_edge=bhi, truth=verdict(ok_all, ok_any))
    row["claims"] = claims
    truths = [c["truth"] for c in claims.values()]
    row["claim_truth"] = "false" if "false" in truths else ("undetermined" if "undetermined" in truths else "true")
    # certificate outcome: Bloch from the first pass, static from the guarded re-run when available
    pr = phase.get(h)
    st_pass = pr["passed"] if pr else (rr["passed"] if rr else s["passed"])
    b = d["cert"].get("bloch")
    bl_pass = b["passed"] if b else True
    row.update(static_passed=st_pass, bloch_passed=bl_pass if b else None, passed=bool(st_pass and bl_pass))
    src = pr or rr
    if src:
        row["static_used"], row["static_fails"] = src["used"], src.get("checks_failed")
    if pr and pr.get("lower_over_finest_min"):
        row["lower_over_finest_min"] = pr["lower_over_finest_min"]
    if b:
        row["count_failures"] = {n: v["n_failures"] for n, v in b["counts"].items()}
    if row["passed"]:
        row["cls"] = "accepted" + (" (claim FALSE: unsound)" if row["claim_truth"] == "false" else "")
    elif row["claim_truth"] == "false":
        row["cls"] = "correct refusal (claim false)"
    elif row["claim_truth"] == "undetermined":
        row["cls"] = "undetermined (reference not converged at this margin)"
    elif b and not bl_pass:
        row["cls"] = ("false alarm (resolution)" if any(row["count_failures"].values())
                      else "false alarm (guard)")
    else:
        row["cls"] = "false alarm (static)"
    rows.append(row)

json.dump(rows, open("results/g2/classification.json", "w"), indent=1, default=float)
from collections import Counter
print(Counter(r["cls"] for r in rows))
for r in rows:
    if r["cls"] != "accepted":
        bad = {k: c["truth"] for k, c in r["claims"].items() if c["truth"] != "true"}
        print(f"{r['cls']:<52} {r['kind']:<16} {json.dumps(r['params']):<28} static {r['static_passed']} "
              f"bloch {r['bloch_passed']} {bad}")
