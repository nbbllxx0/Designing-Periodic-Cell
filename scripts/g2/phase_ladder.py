"""G2 fix, calibration data: static values over resolutions AND grid phases, for cells outside the 50 G2 cells
(held-out set, so the static guard is not tuned on its own test set), plus a few G2 cells for diagnosis only.

For each cell: n in (32, 48, 64, 80) x phase in (0, 1/8, 1/4, 3/8, 1/2) voxel, and n = 96 at phases (0, 1/2).
Phases in [0, 1/2] suffice for these mirror-symmetric cells (shift s and 1 - s give the mirrored voxelization;
results/g2/phase_study_cube.log: 0.2 and 0.8, 0.4 and 0.6 give identical values).
Output: results/g2/phase_ladder/<hash>.json (resumable), log lines on stdout.
Usage: phase_ladder.py <set>   with set = heldout | diag
"""
import json, os, sys, time
import amm  # noqa: F401
from amm import certify, fem, geometry as G, homog

OUT = "results/g2/phase_ladder"
os.makedirs(OUT, exist_ok=True)
R = lambda k, **p: dict(family="resonator", kind=k, params=p)
L = lambda k, **p: dict(family="struts", kind=k, params=p)
T = lambda k, d, m: dict(family="tpms", kind=k, params=dict(density=d, mode=m))
SETS = {
    # held-out calibration cells (percolating, not in results/g2/selected.json): flat faces, thin struts, TPMS
    "heldout": [R("cube_bars", c=0.6, w=0.15), R("cube_bars", c=0.8, w=0.15), R("cube_bars", c=0.5, w=0.1),
                R("cube_bars", c=0.7, w=0.25), R("sphere_ligaments", c=0.25, w=0.15),
                R("sphere_ligaments", c=0.35, w=0.25), L("bcc", r=0.06, R=0.15), L("sc", r=0.06, R=0.15),
                L("octet", r=0.06, R=0.22), T("diamond", 0.15, "network"), T("iwp", 0.5, "sheet")],
    # G2 cells, diagnosis of the remaining unsound bound only (not used to set any constant)
    "diag": [R("cube_bars", c=0.7, w=0.15)],
}
PLAN = [(n, p) for n in (32, 48, 64, 80) for p in (0.0, 0.125, 0.25, 0.375, 0.5)] + [(96, 0.0), (96, 0.5)]


for spec in SETS[sys.argv[1]]:
    h = certify.spec_hash(spec)
    path = f"{OUT}/{h}.json"
    rec = json.load(open(path)) if os.path.exists(path) else dict(spec=spec, rows={})
    for n, p in PLAN:
        key = f"{n}@{p}"
        if key in rec["rows"]:
            continue
        t0 = time.perf_counter()
        cov, sub, info = G.design_cell(spec, n, phase=p)
        r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub))
        rec["rows"][key] = dict(density=float(info["density"]), percolates=bool(all(info["percolates"])),
                                **{q: float(r[q]) for q in ("E100", "G", "bulk", "nu100")},
                                s=round(time.perf_counter() - t0, 1))
        json.dump(rec, open(path, "w"), indent=1)
        print(json.dumps(dict(kind=spec["kind"], params=spec["params"], key=key, **rec["rows"][key])), flush=True)
