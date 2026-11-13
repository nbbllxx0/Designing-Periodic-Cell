"""G2 fix: evaluate candidate static guards on the phase-ladder data (results/g2/phase_ladder/, held-out cells).

Candidates, per quantity, on a rung (n1, n2, n3):
  current   phase 0 at n1, n2, n3 + phases {0.25, 0.5} at n3 (certify.static_convergence as of the first G2 run)
  mean3     mean over phases {0, 0.25, 0.5} at every n of the rung; order fitted from the three means (capped at
            P_MAX); lower = min(all values, ext - s * remaining), remaining = |d23| h3^p / (h2^p - h3^p)
  mean5     the same with phases {0, 1/8, 1/4, 3/8, 1/2}
Limit estimate for scoring: fitted-order extrapolation of the 5-phase means at (48, 64, 80) and, where present,
O(h) of the mean of the n = 96 phases against n = 80; also the smallest computed value anywhere (an upper bound
on the limit, since stiffness converges from above). A lower bound above that smallest value is unsound for certain.
Prints, per cell and quantity: lower / limit_estimate - 1 for each candidate, and the margin a claim needs
(values / lower - 1).
"""
import glob, json, sys
import numpy as np
from scipy.optimize import brentq

S, P_MAX, P_MIN = 2.0, 2.0, 0.25
Q = ("E100", "G", "bulk")


def order(h, f):
    d12, d23 = f[1] - f[0], f[2] - f[1]
    if d12 == 0 or d23 == 0 or d12 * d23 < 0 or abs(d23) >= abs(d12):
        return None
    g = lambda p: (h[1] ** p - h[2] ** p) / (h[0] ** p - h[1] ** p) - d23 / d12
    try:
        return brentq(g, P_MIN, 8.0)
    except ValueError:
        return None


def mean_guard(ns, means, allv, spread, s=S):
    h = [1 / n for n in ns]
    d12, d23 = means[1] - means[0], means[2] - means[1]
    p = order(h, means)
    if p is not None:
        pu = min(p, P_MAX)
        r = h[2] ** pu / (h[1] ** pu - h[2] ** pu)
        ext, err = means[2] + d23 * r, abs(d23) * r
    elif abs(d12) <= s * spread and abs(d23) <= s * spread:
        ext, err = means[2], spread
    else:
        return None, None
    return min(*allv, ext - s * err), p


def current_guard(ns, v, ph, s=S):
    (v1, v2, v3) = v
    P = max(ph) - min(ph)
    d12, d23 = v2 - v1, v3 - v2
    strict = d12 * d23 > 0 and abs(d23) < abs(d12)
    ext = v3 + d23 * (1 / ns[2]) / (1 / ns[1] - 1 / ns[2]) if strict else v3
    return min(v1, v2, v3, *ph, ext - s * abs(d23), min(ph) - s * P)


import amm  # noqa: E402,F401
from amm import certify  # noqa: E402

PH = {3: (0.0, 0.25, 0.5), 5: (0.0, 0.125, 0.25, 0.375, 0.5)}
summary = []
for path in sorted(glob.glob("results/g2/phase_ladder/*.json")):
    rec = json.load(open(path))
    rows = rec["rows"]
    if not all(f"80@{p}" in rows for p in PH[5]):
        continue
    print(rec["spec"]["kind"], rec["spec"]["params"])
    for q in Q:
        val = lambda n, p: rows[f"{n}@{p}"][q]
        m5 = {n: np.mean([val(n, p) for p in PH[5]]) for n in (32, 48, 64, 80)}
        finest_min = min(v[q] for v in rows.values())
        ns = (48, 64, 80)
        p_ref = order([1 / n for n in ns], [m5[n] for n in ns])
        lim = m5[80] + (m5[80] - m5[64]) * ((1 / 80) ** p_ref / ((1 / 64) ** p_ref - (1 / 80) ** p_ref)) if p_ref             else m5[80] + (m5[80] - m5[64]) * 4  # O(h) when no order can be fitted
        lim96 = None
        if "96@0.0" in rows and "96@0.5" in rows:
            m96 = 0.5 * (val(96, 0.0) + val(96, 0.5))
            lim96 = m96 + (m96 - 0.5 * (val(80, 0.0) + val(80, 0.5))) * 5
        est = min(x for x in (lim, lim96, finest_min) if x is not None)
        line = [f"  {q:<5} est {est:.5g} (p={p_ref and round(p_ref, 2)}, 96:{lim96 and round(lim96, 6)}, min {finest_min:.5g})"]
        for rung in ((32, 48, 64), (48, 64, 80)):
            cur = current_guard(rung, [val(n, 0.0) for n in rung], [val(rung[-1], p) for p in (0.0, 0.25, 0.5)])
            parts = [f"cur {cur / est - 1:+.3f}"]
            for K in (3, 5):
                c = certify.static_convergence({n: [dict((qq, rows[f"{n}@{p}"][qq]) for qq in certify.STATIC_QUANTITIES)
                                                    for p in PH[K]] for n in rung})["quantities"][q]
                parts.append(f"K{K} {c['lower'] / est - 1:+.3f}{'' if c['converged'] else '(nc)'} need {1 - c['lower'] / c['means'][-1]:.3f}")
                summary.append(dict(cell=rec["spec"], q=q, rung=rung, K=K, sound=c["lower"] <= est,
                                    over=c["lower"] / est - 1, conv=c["converged"], need=1 - c["lower"] / c["means"][-1]))
            line.append(f"{rung}: " + " ".join(parts))
        print(" | ".join(line))
for K in (3, 5):
    for rung in ((32, 48, 64), (48, 64, 80)):
        sub = [x for x in summary if x["K"] == K and x["rung"] == rung]
        if sub:
            conv = [x for x in sub if x["conv"]]
            print(f"K={K} {rung}: unsound {sum(not x['sound'] for x in sub)}/{len(sub)} "
                  f"(worst {max(x['over'] for x in sub):+.3f}); converged {len(conv)}; "
                  f"need >5% margin {sum(x['need'] > 0.05 for x in conv)}")
