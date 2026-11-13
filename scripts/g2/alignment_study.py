"""G2 follow-up: does grid alignment bias the static values of cube_bars (c = 0.7, w = 0.2)?
The cube and bar faces lie on voxel faces only when 0.7 n and 0.2 n are integers (n a multiple of 10 here);
otherwise the boundary voxels are partial (finite-cell coverage). Output: results/g2/alignment_study.json"""
import json, sys, time
import amm  # noqa: F401
from amm import fem, geometry as G, homog

spec = dict(family="resonator", kind="cube_bars", params=dict(c=0.7, w=0.2))
out = []
for n in [int(x) for x in sys.argv[1:]]:
    t0 = time.perf_counter()
    cov, sub, info = G.design_cell(spec, n)
    r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub))
    row = dict(n=n, aligned=bool(abs(0.7 * n - round(0.7 * n)) < 1e-9 and abs(0.2 * n - round(0.2 * n)) < 1e-9),
               **{q: float(r[q]) for q in ("density", "E100", "G", "bulk", "nu100")}, s=round(time.perf_counter() - t0, 1))
    out.append(row)
    print(json.dumps(row), flush=True)
json.dump(dict(spec=spec, rows=out), open("results/g2/alignment_study.json", "w"), indent=1)
