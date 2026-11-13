"""V13 (audit-loop round 3, 2026-11-09): the gap guard with monotone drift taken out of the phase-noise branch
(theory reviewer #6, domain reviewer #4).

In the current guard (amm.bloch._edge_guard) an edge sequence with no admissible fitted order (step not
shrinking, or order outside [0.25, 8]) is bounded by the phase spread P when both steps lie within safety * P.
A monotone sequence can land in that branch, so a slow drift is treated as noise. Three stricter variants keep
the order-fit branch unchanged and change only monotone sequences in the noise branch:
  abstain_toward  a drift toward the claim (lower edge rising, upper edge falling) gives no safe edge;
  extrap_p1       extrapolate at order 1: ext = f3 + d23 r, err = max(P, |d23| r), r = h3^p / (h2^p - h3^p);
  extrap_p025     the same at the order floor P_MIN = 0.25.
The safe edge is then ext moved inward by safety * err, with the computed and phase values as candidates, as in
the order-fit branch. For cells with a converged reference the reference edges are listed beside the safe edges.

Applied to stored edge sequences only (no solves):
  * the twelve certified gaps of Section 5.2 (same inputs as v12_gap_guard_audit.py);
  * every three-resolution gap block among the 85 unique certificates of the search benchmark.

    python scripts/experiments/v13_monotone_rule.py
Writes results/verification/v13/monotone_rule.json. CPU only, seconds, no LLM.
"""
import glob
import json
import sys
from pathlib import Path

import amm  # noqa: F401
from amm import bloch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v13"
sys.path.insert(0, str(ROOT / "scripts/experiments"))
from v12_gap_guard_audit import cases  # noqa: E402

P_FLOOR = bloch.P_MIN


def guard(ns, f, ph, side, variant):
    """variant: current | abstain_toward (monotone drift toward the claim -> no safe edge) |
    extrap_p025 / extrap_p1 (monotone -> extrapolate at that order; error = max(P, remaining))."""
    safe, info = bloch._edge_guard(ns, f, ph, bloch.CONVERGENCE_SAFETY, side)
    d12, d23 = f[1] - f[0], f[2] - f[1]
    monotone = d12 * d23 > 0
    toward = monotone and ((side == "lo" and d23 > 0) or (side == "hi" and d23 < 0))
    branch = "none" if safe is None else ("order fit" if info.get("p") is not None else "phase noise")
    if safe is not None and branch == "phase noise" and variant != "current":
        if variant == "abstain_toward":
            if toward:
                safe = None
        elif monotone:
            p = 0.25 if variant == "extrap_p025" else 1.0
            h = [1 / n for n in ns]
            r = h[2] ** p / (h[1] ** p - h[2] ** p)
            ext, err = f[2] + d23 * r, max(info["phase_spread"], abs(d23) * r)
            sgn = 1 if side == "lo" else -1
            cands = list(f) + list(ph) + [ext + sgn * bloch.CONVERGENCE_SAFETY * err]
            safe = max(cands) if side == "lo" else min(cands)
    return safe, branch, monotone, toward


VARIANTS = ("current", "abstain_toward", "extrap_p1", "extrap_p025")


def judge(edges, phase, claim):
    items = sorted(((int(n), v) for n, v in edges.items()))[-3:]
    ns = [n for n, _ in items]
    ph_lo = [e[0] for e in phase] if phase else []
    ph_hi = [e[1] for e in phase] if phase else []
    out = {}
    for v in VARIANTS:
        lo, blo, mlo, tlo = guard(ns, [x[0] for _, x in items], ph_lo, "lo", v)
        hi, bhi, mhi, thi = guard(ns, [x[1] for _, x in items], ph_hi, "hi", v)
        ok = lo is not None and hi is not None and lo < hi and claim[0] >= lo and claim[1] <= hi
        out[v] = dict(safe=[lo, hi], inside=bool(ok))
    out["branches"] = [blo, bhi]
    out["monotone"] = [mlo, mhi]
    out["toward_claim"] = [tlo, thi]
    return out

def main():
    res = dict(variants=dict(
        current="as released",
        abstain_toward="phase-noise edge drifting monotonically toward the claim -> undetermined",
        extrap_p1="monotone phase-noise edge -> first-order extrapolation, error max(P, remaining), safety 2",
        extrap_p025="monotone phase-noise edge -> extrapolation at the order floor 0.25, error max(P, remaining)"))
    ref = {r["case"]: r.get("ref") for r in json.loads((ROOT / "results/verification/v12/gap_guard_audit.json").read_text())}
    rows = []
    for c in cases():
        j = judge(c["edges"], c["phase"], c["claim"])
        rows.append(dict(case=c["case"], src=c["src"], claim=c["claim"], ref=ref.get(c["case"]), **j))
    res["certified_gaps"] = rows
    res["certified_gaps_summary"] = {
        v: dict(certified=sum(r[v]["inside"] for r in rows),
                changed=[r["case"] for r in rows if r["current"]["inside"] and not r[v]["inside"]],
                changed_with_reference=[r["case"] for r in rows
                                        if r["current"]["inside"] and not r[v]["inside"] and r["ref"]])
        for v in VARIANTS}
    res["noise_branch_edges"] = dict(
        n_edges=2 * len(rows), noise=sum(b == "phase noise" for r in rows for b in r["branches"]),
        noise_monotone=sum(b == "phase noise" and m for r in rows for b, m in zip(r["branches"], r["monotone"])),
        noise_toward=sum(b == "phase noise" and t for r in rows for b, t in zip(r["branches"], r["toward_claim"])),
        toward_cases=[(r["case"], s) for r in rows for b, t, s in zip(r["branches"], r["toward_claim"], ("lo", "hi"))
                      if b == "phase noise" and t])

    bench = []
    for f in sorted(glob.glob(str(ROOT / "results/verification/v3/certs/*.json"))):
        if f.endswith(".summary.json"):
            continue
        d = json.loads(Path(f).read_text())
        b = d["blocks"].get("bloch") or {}
        conv = b.get("convergence") or {}
        if conv.get("mode") != "three-resolution":
            continue
        cl = b["claim"]
        j = judge(conv["edges"], conv.get("phase_edges"), [cl["f_lo"], cl["f_hi"]])
        bench.append(dict(cert=Path(f).name, cert_verdict=d["verdict"],
                          gap_verdict=(b.get("verdict") or {}).get("verdict"), **j))
    res["benchmark"] = bench
    res["benchmark_summary"] = dict(
        n_three_resolution_gap_blocks=len(bench),
        certificates_certified=sum(x["cert_verdict"] == "certified" for x in bench),
        stored_certified_implies_current_inside=all(x["current"]["inside"] for x in bench
                                                    if x["gap_verdict"] == "certified"),
        **{f"certified_kept_{v}": sum(x["cert_verdict"] == "certified" and x[v]["inside"] for x in bench)
           for v in VARIANTS},
        **{f"changed_{v}": [x["cert"] for x in bench if x["cert_verdict"] == "certified" and not x[v]["inside"]]
           for v in VARIANTS})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "monotone_rule.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["certified_gaps_summary"], indent=1))
    print(json.dumps(res["noise_branch_edges"], indent=1))
    print(json.dumps(res["benchmark_summary"], indent=1))
    for r in rows:
        s = lambda v: [round(x, 4) if x is not None else None for x in r[v]["safe"]]
        print(f"{r['case']:30s} {r['branches']} toward {r['toward_claim']} claim {[round(x, 4) for x in r['claim']]} "
              f"ref {[round(x, 4) for x in r['ref']] if r['ref'] else None} cur {s('current')} p1 {s('extrap_p1')} "
              f"p025 {s('extrap_p025')}")


if __name__ == "__main__":
    main()