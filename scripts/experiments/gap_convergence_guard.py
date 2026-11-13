"""Discretization guard of the gap certificate on the Lucklum & Vellekoop (2018) cell (ball 0.79a, beam 0.05a).

Both gap edges converge from above with resolution, so the inertia counts at n = 20 and 30 alone accept an upper
edge up to ~0.478 f a / c_l although the converged edge is ~0.470 (paper 0.4702). With the convergence guard the
claim must also lie inside the extrapolated safe interval. Claims are given in f a / c_l and converted to f*.
"""
import json, time
import numpy as np
import amm  # noqa: F401
from amm import bloch, fem, geometry as G

NU = 0.35
CL_OVER_CT = np.sqrt(2 * (1 - NU) / (1 - 2 * NU))
SPEC = dict(family="resonator", kind="sphere_ligaments", params=dict(c=0.395, w=0.05))
CLAIMS = {"overstated_upper_0.478": (0.055, 0.478), "conservative_0.46": (0.055, 0.46)}

meshes = {}
for n in (20, 30):
    cov, sub, info = G.design_cell(SPEC, n)
    meshes[n] = fem.build_mesh(cov, sub=sub, nu=NU)
out = {}
for name, (lo, hi) in CLAIMS.items():
    t = time.perf_counter()
    for conv in (False, True):
        r = bloch.certify_gap(meshes, lo * CL_OVER_CT, hi * CL_OVER_CT, convergence=conv)
        key = f"{name}|guard={conv}"
        row = dict(claim_fa_over_cl=[lo, hi], passed=r["passed"],
                   counts_passed={n: v["passed"] for n, v in r["resolutions"].items()},
                   below_band=r["claim"]["below_band"], seconds=round(time.perf_counter() - t, 1))
        if "convergence" in r:
            c = r["convergence"]
            row.update(edges_fa_over_cl={n: [round(x / CL_OVER_CT, 4) for x in e] for n, e in c["edges"].items()},
                       extrapolated_fa_over_cl=[round(x / CL_OVER_CT, 4) for x in c["extrapolated"]],
                       safe_interval_fa_over_cl=[round(x / CL_OVER_CT, 4) for x in c["safe_interval"]])
        out[key] = row
        print(key, json.dumps(row), flush=True)
json.dump(out, open("results/verification/gap_convergence_guard.json", "w"), indent=1, default=float)
