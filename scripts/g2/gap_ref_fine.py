"""G2 follow-up: is the gap reference itself converged?

The first pass took the reference edges from n = 30 and 40, extrapolated at O(h). Several resonator cells were
refused, and their edges still move by several percent between 30 and 40. This script adds n = 50 and then 60, so
the convergence order can be estimated from more resolutions instead of assumed.

Reference k set (as in the first pass): the symmetry points G, X, M, R and the scan's extremum k-points.
Method:
  1. At n = 30 (cheap), FP64 shift-invert Lanczos (`InertiaCounter.edge`) for both edges at every k of the set.
     The two k-points with the highest lower edge and the two with the lowest upper edge are kept.
  2. At n = 40, 50, 60, Lanczos only at those kept k-points. The n = 40 values must reproduce the first-pass
     reference (which screened every k of the set with inertia counts), which checks that the kept points
     contain the extremum.
  The fine resolutions are not re-screened, so they assume the extremum stays among the two kept points.
  A first attempt that used only the n = 12 scan's extremum k was wrong for flat resonance bands (the extremum
  sits at another symmetry point at finer n); its values were discarded.
Output: results/g2/gap_ref_fine/<hash>.json (resumable).
"""
import glob, json, os, sys, time
import numpy as np
import amm  # noqa: F401
from amm import bloch, certify, fem, geometry as G

OUT = "results/g2/gap_ref_fine"
os.makedirs(OUT, exist_ok=True)
NS = tuple(int(x) for x in sys.argv[1:]) or (40, 50, 60)

cells = []
for f in sorted(glob.glob("results/g2/cells/*_m0.05.json")):
    d = json.load(open(f))
    if d.get("gap_ref", {}).get("open"):
        cells.append(d)


def setup(d):
    spec, g = d["spec"], d["scan_gap"]
    path = f"{OUT}/{certify.spec_hash(spec)}.json"
    rec = json.load(open(path)) if os.path.exists(path) else {}
    if rec.get("version") != 2:
        rec = dict(version=2, spec=spec, raw={}, seconds={})
    names = list(bloch.SC_POINTS) + ["scan_k_lo", "scan_k_hi"]
    ks = [np.pi * np.array(v, float) for v in bloch.SC_POINTS.values()] + \
         [np.pi * np.array(g["k_lo"], float), np.pi * np.array(g["k_hi"], float)]
    f_mid = 0.5 * (g["f_lo"] + g["f_hi"])
    if "kept" not in rec:
        t0 = time.perf_counter()
        cov, sub, _ = G.design_cell(spec, 30)
        ic = bloch.InertiaCounter(fem.build_mesh(cov, sub=sub))
        lo = [ic.edge(k, f_mid, "below") for k in ks]
        hi = [ic.edge(k, f_mid, "above") for k in ks]
        ic.free()
        rec["n30_all"] = dict(names=names, lo=lo, hi=hi)
        rec["kept"] = dict(lo=[int(i) for i in np.argsort(lo)[::-1][:2]], hi=[int(i) for i in np.argsort(hi)[:2]])
        rec["raw"]["30"] = [max(lo), min(hi)]
        rec["seconds"]["30"] = round(time.perf_counter() - t0, 1)
        json.dump(rec, open(path, "w"), indent=1)
    return rec, path, ks, f_mid


for n in NS:
    for d in cells:
        rec, path, ks, f_mid = setup(d)
        if str(n) in rec["raw"]:
            continue
        t0 = time.perf_counter()
        cov, sub, _ = G.design_cell(d["spec"], n)
        ic = bloch.InertiaCounter(fem.build_mesh(cov, sub=sub))
        lo = {i: ic.edge(ks[i], f_mid, "below") for i in rec["kept"]["lo"]}
        hi = {i: ic.edge(ks[i], f_mid, "above") for i in rec["kept"]["hi"]}
        ic.free()
        rec["raw"][str(n)] = [max(lo.values()), min(hi.values())]
        rec.setdefault("per_k", {})[str(n)] = dict(lo=lo, hi=hi)
        rec["seconds"][str(n)] = round(time.perf_counter() - t0, 1)
        json.dump(rec, open(path, "w"), indent=1)
        first = d["gap_ref"]["raw"].get(str(n))
        print(json.dumps(dict(kind=d["spec"]["kind"], params=d["spec"]["params"], n=n, edges=rec["raw"][str(n)],
                              first_pass=first, s=rec["seconds"][str(n)])), flush=True)
