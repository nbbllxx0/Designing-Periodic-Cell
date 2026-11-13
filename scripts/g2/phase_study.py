"""G2 follow-up: sensitivity of finite-cell values to the grid phase. The cell is periodic, so translating the
geometry by a fraction of a voxel changes nothing physically; any change in the computed values is discretization
error from where the surfaces cut the voxels. Usage: phase_study.py <family> <kind> <params-json> <n> <shifts...>
(shifts in voxel widths, applied along x, y and z). Output: JSON lines."""
import json, sys, time
import numpy as np
import amm  # noqa: F401
from amm import fem, geometry as G, homog

_grid = G.grid
fam, kind, params, n = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), int(sys.argv[4])
spec = dict(family=fam, kind=kind, params=params)
for d in [float(x) for x in sys.argv[5:]]:
    G.grid = lambda m, d=d: np.meshgrid(*[((np.arange(m) + 0.5) / m + d / n) % 1.0] * 3, indexing="ij")
    t0 = time.perf_counter()
    cov, sub, info = G.design_cell(spec, n)
    r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub))
    print(json.dumps(dict(kind=kind, params=params, n=n, shift=d, density=info["density"],
                          **{q: float(r[q]) for q in ("E100", "G", "bulk", "nu100")}, s=round(time.perf_counter() - t0, 1))), flush=True)
G.grid = _grid
