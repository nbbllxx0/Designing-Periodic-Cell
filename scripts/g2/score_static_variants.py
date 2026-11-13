"""Score static-guard variants on the held-out phase-ladder cells (results/g2/phase_ladder/).
Sure test: a lower bound above any computed value (stiffness converges from above) is unsound for certain.
Estimate test: lower bound above est = O(h) extrapolation of the 5-phase means from the next finer pair
(rung (32,48,64): pair (64,80); rung (48,64,80): pair (80,96) with the 96 mean over phases 0 and 1/2) is likely
unsound. Tightness: 1 - lower / finest mean (the claim margin the guard needs). Variants: P_MAX in {1, 2}."""
import glob, json
import numpy as np
import amm  # noqa: F401
from amm import bloch, certify

import sys
PH = (0.0, 0.25, 0.5) if "k3" in sys.argv else (0.0, 0.125, 0.25, 0.375, 0.5)
res = {}
for pmax in (1.0, 2.0):
    bloch.P_MAX = pmax
    out = []
    for path in sorted(glob.glob("results/g2/phase_ladder/*.json")):
        rec = json.load(open(path)); rows = rec["rows"]
        if "96@0.5" not in rows:
            continue
        for q in ("E100", "G", "bulk"):
            m = {n: np.mean([rows[f"{n}@{p}"][q] for p in PH]) for n in (32, 48, 64, 80)}
            m[96] = np.mean([rows["96@0.0"][q], rows["96@0.5"][q]])
            mn = min(v[q] for v in rows.values())
            for rung, (a, b) in (((32, 48, 64), (64, 80)), ((48, 64, 80), (80, 96))):
                c = certify.static_convergence({n: [{qq: rows[f"{n}@{p}"][qq] for qq in certify.STATIC_QUANTITIES}
                                                     for p in PH] for n in rung})["quantities"][q]
                est = m[b] + (m[b] - m[a]) * (1 / b) / (1 / a - 1 / b)
                out.append(dict(cell=f"{rec['spec']['kind']} {rec['spec']['params']}", q=q, rung=rung,
                                conv=c["converged"], sure=c["lower"] > mn, over=c["lower"] / est - 1,
                                need=1 - c["lower"] / c["means"][-1]))
    res[pmax] = out
    for rung in ((32, 48, 64), (48, 64, 80)):
        s = [x for x in out if x["rung"] == rung]
        cv = [x for x in s if x["conv"]]
        bad = [x for x in cv if x["over"] > 0]
        print(f"P_MAX={pmax} {rung}: {len(s)} cases, converged {len(cv)}, sure-unsound {sum(x['sure'] for x in s)}, "
              f"above O(h) estimate (converged) {len(bad)} worst {max([x['over'] for x in cv], default=0):+.3f}, "
              f"need>5% {sum(x['need'] > 0.05 for x in cv)}, median need {np.median([x['need'] for x in cv]):.3f}")
        for x in bad:
            print(f"    {x['cell']} {x['q']} over {x['over']:+.3f} need {x['need']:.3f}")
