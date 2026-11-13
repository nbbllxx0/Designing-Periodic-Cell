"""V20 (2026-11-10): grid-convergence-index (GCI) baselines on the near-threshold claims of V13 (confirm-round
reviewers: editor #1, domain #5, theory #6: "compare the guard with the GCI practice it follows, not only with an
unguarded single solve").

Same claims, same stored solves as results/verification/v13/near_threshold.json (50 development cells,
results/g2/rerun_v3; truth = the amm reference bracket of results/g2/classification_v3.json). The stored records keep
the phase means of the three resolutions of the rung each certificate used, not the phase-0 values, so every rule
below sees the same three phase means m1 (coarsest) .. m3 (finest) that the guard uses; this favours GCI.

Rules (Roache 1994; three-grid procedure of Celik et al. 2008, J. Fluids Eng. 130:078001, with non-constant ratios):
  GCI-1.25: observed order p from the three means (fixed-point iteration on |e32/e21| with the sign term), Fs = 1.25;
            band f3 +- Fs |f3 - f2| / (r^p - 1); if p cannot be computed (zero change, no convergence of the
            iteration, p outside [0.25, 8]) the two finest grids are used with p = 1 and Fs = 3.
  GCI-3:    two finest grids, assumed p = 1, Fs = 3.
A minimum claim is accepted when f3 - band >= target, a maximum when f3 + band <= target. For gap claims the band of
each edge is computed the same way from its stored three-resolution edges (lower edge: accept when lo3 + band <= claim
start; upper: hi3 - band >= claim end).

    python scripts/experiments/v20_gci_baseline.py
Output: results/verification/v20/gci_baseline.json. Stored data only; CPU seconds; no GPU, no LLM.
"""
import collections
import glob
import json
import math
from pathlib import Path

import amm  # noqa: F401
from amm import certify

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v20"
DS = (0.005, 0.01, 0.02, 0.03, 0.05)
STATIC = {"E100_min": ("E100", "min"), "G_min": ("G", "min"), "density_max": ("density", "max")}


def observed_order(ns, f):
    """Celik et al. (2008) observed order for grids n1 < n2 < n3 (h = 1/n), or None."""
    h1, h2, h3 = (1 / n for n in ns)  # h1 coarsest
    r21, r32 = h2 / h3, h1 / h2  # fine-to-medium, medium-to-coarse (Celik: r21 = h2/h1 with 1 the finest)
    e21, e32 = f[2] - f[1], f[1] - f[0]
    if e21 == 0 or e32 == 0:
        return None
    s = math.copysign(1.0, e32 / e21)
    p = 1.0
    for _ in range(200):
        try:
            q = math.log((r21 ** p - s) / (r32 ** p - s))
            pn = abs(math.log(abs(e32 / e21)) + q) / math.log(r21)
        except (ValueError, ZeroDivisionError):
            return None
        if abs(pn - p) < 1e-10:
            p = pn
            break
        p = pn
    else:
        return None
    return p if 0.25 <= p <= 8 else None


def band(ns, f):
    """(band half-width around f3, rule used)."""
    r21 = ns[2] / ns[1]
    p = observed_order(ns, f)
    if p is not None:
        return 1.25 * abs(f[2] - f[1]) / (r21 ** p - 1), "observed p, Fs 1.25"
    return 3.0 * abs(f[2] - f[1]) / (r21 - 1), "fallback p 1, Fs 3"


def band3(ns, f):
    return 3.0 * abs(f[2] - f[1]) / (ns[2] / ns[1] - 1), "p 1, Fs 3"


def main():
    truth = {(r["kind"], json.dumps(r["params"], sort_keys=True)): r
             for r in json.loads((ROOT / "results/g2/classification_v3.json").read_text())}
    rows = []
    for f in sorted(glob.glob(str(ROOT / "results/g2/rerun_v3/*.json"))):
        r3 = json.loads(Path(f).read_text())
        spec = r3["spec"]
        t = truth.get((spec["kind"], json.dumps(spec["params"], sort_keys=True)))
        if t is None:
            continue
        st = r3["static"]
        conv = st.get("convergence")
        ns = sorted(st.get("used") or [])[-3:]
        for key, (q, kind) in STATIC.items():
            cl = t["claims"].get(key)
            if cl is None or cl.get("bracket") is None:
                continue
            if conv and len(ns) == 3:
                m = conv[q]["means"]
                b125, rule = band(ns, m)
                b3, _ = band3(ns, m)
            else:  # no stored three-resolution means: no rule can accept (same claim set as V13)
                m, b125, b3, rule = [float("nan")] * 3, float("inf"), float("inf"), "no stored means"
            lo, hi = cl["bracket"]
            for d in DS:
                for tr in ("true", "false"):
                    if kind == "min":
                        tgt = lo * (1 - d) if tr == "true" else hi * (1 + d)
                        acc = lambda b: m[-1] - b >= tgt
                    else:
                        tgt = hi * (1 + d) if tr == "true" else lo * (1 - d)
                        acc = lambda b: m[-1] + b <= tgt
                    if not conv:
                        rows.append(dict(cell=Path(f).stem, block="static", key=key, d=d, truth=tr, checker=False,
                                         naive=False, gci125=False, gci3=False, gci125_rule=rule))
                        continue
                    v = certify.static_verdict(conv, {key: tgt}, bool(st.get("numerics_ok")))["targets"][key]
                    rows.append(dict(cell=Path(f).stem, block="static", key=key, d=d, truth=tr,
                                     checker=v == "certified", naive=bool(m[-1] >= tgt if kind == "min" else m[-1] <= tgt),
                                     gci125=bool(acc(b125)), gci3=bool(acc(b3)), gci125_rule=rule))
        b = r3.get("bloch") or {}
        if b.get("convergence"):
            b = certify.rescore_bloch(b, spec)
        c = b.get("convergence") or {}
        g = t["claims"].get("gap")
        if c.get("mode") == "three-resolution" and g and c.get("safe_interval"):
            s_lo, s_hi = c["safe_interval"]
            ek = sorted(c["edges"], key=int)[-3:]
            ens = [int(n) for n in ek]
            lo_seq = [c["edges"][n][0] for n in ek]
            hi_seq = [c["edges"][n][1] for n in ek]
            bl125, _ = band(ens, lo_seq)
            bh125, _ = band(ens, hi_seq)
            bl3, _ = band3(ens, lo_seq)
            bh3, _ = band3(ens, hi_seq)
            L, U = g["lower_edge"], g["upper_edge"]
            for d in DS:
                for tr, (a, z) in (("true", (L["hi"] * (1 + d), U["lo"] * (1 - d))),
                                   ("false_lo", (L["lo"] * (1 - d), U["lo"] * (1 - d))),
                                   ("false_hi", (L["hi"] * (1 + d), U["hi"] * (1 + d)))):
                    if a >= z:
                        continue
                    cert = s_lo is not None and s_hi is not None and s_lo < s_hi and a >= s_lo and z <= s_hi
                    rows.append(dict(cell=Path(f).stem, block="gap", key="gap", d=d,
                                     truth="true" if tr == "true" else "false", checker=bool(cert),
                                     naive=bool(a >= lo_seq[-1] and z <= hi_seq[-1]),
                                     gci125=bool(lo_seq[-1] + bl125 <= a and hi_seq[-1] - bh125 >= z),
                                     gci3=bool(lo_seq[-1] + bl3 <= a and hi_seq[-1] - bh3 >= z)))
    summ = {}
    for blk in ("static", "gap"):
        rs = [r for r in rows if r["block"] == blk]
        s = dict(n_claims=len(rs), n_true=sum(r["truth"] == "true" for r in rs),
                 n_false=sum(r["truth"] == "false" for r in rs))
        for rule in ("checker", "naive", "gci125", "gci3"):
            s[rule] = dict(false_accepted=sum(r["truth"] == "false" and r[rule] for r in rs),
                           true_accepted=sum(r["truth"] == "true" and r[rule] for r in rs),
                           false_by_d={str(d): sum(r["truth"] == "false" and r[rule] and r["d"] == d for r in rs)
                                       for d in DS})
        if blk == "static":
            s["gci125_rules"] = dict(collections.Counter(r["gci125_rule"] for r in rs))
        summ[blk] = s
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gci_baseline.json").write_text(json.dumps(dict(summary=summ, rows=rows), indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
