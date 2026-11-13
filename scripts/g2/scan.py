"""G2 step 1: scan cell families with the GPU search tier (n = 12) on a dense k set.

For every complete gap, compare the edges from the irreducible-zone path alone with the edges from path + 300
interior points. A positive `interior_excess` means an interior k carries a band extremum beyond the path ones,
i.e. a gap claim built from the path alone could be false (candidate for the interior-k mutation).
Output: results/g2/scan.json (one row per percolating cell).
"""
import json, itertools, time
import numpy as np
import amm  # noqa: F401
from amm import bloch, fem, geometry as G

N, NEV = 12, 18
SPECS = []
SPECS += [dict(family="resonator", kind="cube_bars", params=dict(c=c, w=w))
          for c, w in itertools.product((0.4, 0.5, 0.6, 0.7, 0.8), (0.1, 0.15, 0.2, 0.25, 0.3))]
SPECS += [dict(family="resonator", kind="sphere_ligaments", params=dict(c=c, w=w))
          for c, w in itertools.product((0.2, 0.25, 0.3, 0.35, 0.4), (0.1, 0.15, 0.2, 0.25))]
SPECS += [dict(family="tpms", kind=k, params=dict(density=d, mode=m))
          for k, d, m in itertools.product(G.TPMS, (0.15, 0.25, 0.35, 0.5), ("network", "sheet"))]
SPECS += [dict(family="struts", kind=k, params=dict(r=r, R=R))
          for k, r, R in itertools.product(G.STRUTS, (0.06, 0.1), (0.0, 0.15, 0.22))]

kp, _ = bloch.kpath(8)
ki = bloch.ibz_interior(300, seed=1)
ks = np.vstack([kp, ki])
rows = []
t0 = time.perf_counter()
for spec in SPECS:
    cov, sub, info = G.design_cell(spec, N)
    row = dict(spec=spec, density=info["density"], percolates=all(info["percolates"]))
    if not row["percolates"]:
        rows.append(row)
        continue
    f = bloch.GPUBands(fem.build_mesh(cov, sub=sub), device="cuda")(ks, nev=NEV)
    gp = []
    for g in bloch.gaps(f, min_rel=0.02):
        j = g["below_band"]
        lo_p, hi_p = float(f[:len(kp), j - 1].max()), float(f[:len(kp), j].min())
        gp.append(dict(g, lo_path=lo_p, hi_path=hi_p,
                       interior_excess=max(g["f_lo"] - lo_p, hi_p - g["f_hi"]) / (g["f_hi"] - g["f_lo"]),
                       k_lo=np.round(ks[f[:, j - 1].argmax()] / np.pi, 3).tolist(),
                       k_hi=np.round(ks[f[:, j].argmin()] / np.pi, 3).tolist()))
    # path-only gaps that the interior closes completely
    closed = []
    for j in range(1, NEV - 1):
        lo_p, hi_p = float(f[:len(kp), j - 1].max()), float(f[:len(kp), j].min())
        if hi_p > lo_p and 2 * (hi_p - lo_p) / (hi_p + lo_p) > 0.02 and not any(x["below_band"] == j for x in gp):
            closed.append(dict(below_band=j, lo_path=lo_p, hi_path=hi_p))
    row.update(gaps=gp, path_only_gaps_closed_inside=closed)
    rows.append(row)
    print(spec["kind"], spec["params"], len(gp), "gaps", "max excess",
          round(max([x["interior_excess"] for x in gp], default=0), 3), "closed", len(closed), flush=True)
json.dump(rows, open("results/g2/scan.json", "w"), indent=1, default=float)
print("cells", len(rows), "seconds", round(time.perf_counter() - t0, 1))
