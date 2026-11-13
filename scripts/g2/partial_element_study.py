"""G2 follow-up: partial-voxel element treatment. Full voxels use hex8i (incompatible modes); finite-cell partial
voxels used plain trilinear sub-cell integration, which locks in bending. Variants, same geometry and coverage:
  fcm_hex8    current: chi-weighted trilinear tables (fem.fcm_tables)
  voigt_hex8i coverage-scaled hex8i (no sub-voxel placement of the solid)
  fcm_hex8i   chi-weighted hex8i: K = Kuu - Kua Kaa^+ Kau with all three blocks chi-integrated (midpoint rule)
Usage: partial_element_study.py <family> <kind> <params-json> n1 n2 ...   Output: appended JSON lines."""
import itertools, json, sys, time
import numpy as np
import amm  # noqa: F401
from amm import fem, geometry as G, homog

_T = {}
def tables_i(h, D, s):
    key = (h, s, D.tobytes())
    if key not in _T:
        c = -1 + (2 * np.arange(s) + 1) / s
        w = (h / s) ** 3
        uu, ua, aa = [], [], []
        for p in itertools.product(c, c, c):
            p = np.array(p); B = fem.B_at(p, h); Ba = fem.bubble_B(p, h)
            uu.append((B.T @ D @ B * w).ravel()); ua.append((B.T @ D @ Ba * w).ravel()); aa.append((Ba.T @ D @ Ba * w).ravel())
        _T[key] = tuple(np.array(x) for x in (uu, ua, aa))
    return _T[key]

def mesh_variant(cov, sub, nu, variant):
    if variant == "voigt_hex8i":
        return fem.build_mesh(cov, sub=None, nu=nu)
    m = fem.build_mesh(cov, sub=sub, nu=nu)
    if variant == "fcm_hex8i":
        part = np.flatnonzero(m.weights < 1 - 1e-12)
        s = sub.shape[1]; i, j, k = m.el_ijk[part].T
        chi = sub[i, :, j, :, k, :].reshape(len(part), s ** 3)
        uu, ua, aa = tables_i(m.h, fem.elastic_D(1.0, nu), s)
        Kuu = (chi @ uu).reshape(-1, 24, 24); Kua = (chi @ ua).reshape(-1, 24, 9); Kaa = (chi @ aa).reshape(-1, 9, 9)
        K = Kuu - Kua @ np.linalg.pinv(Kaa, rcond=1e-10, hermitian=True) @ Kua.transpose(0, 2, 1)
        m.Ke[part] = 0.5 * (K + K.transpose(0, 2, 1))
    return m

fam, kind, params = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
spec = dict(family=fam, kind=kind, params=params)
for n in [int(x) for x in sys.argv[4:]]:
    cov, sub, info = G.design_cell(spec, n)
    for v in ("fcm_hex8", "voigt_hex8i", "fcm_hex8i"):
        t0 = time.perf_counter()
        r = homog.homogenize(mesh=mesh_variant(cov, sub, 0.3, v))
        print(json.dumps(dict(kind=kind, params=params, n=n, variant=v, **{q: float(r[q]) for q in ("E100", "G", "bulk")},
                              residual=float(r["max_residual"]), min_eig=float(r["min_eig"]), s=round(time.perf_counter() - t0, 1))), flush=True)
