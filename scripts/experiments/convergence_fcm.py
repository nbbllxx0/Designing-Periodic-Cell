"""Static and gap-edge convergence with finite-cell partial voxels (cube_bars c=0.6 w=0.2, and a non-aligned c=0.57 w=0.17)."""
import time, numpy as np, scipy.sparse as sp
from scipy.sparse.linalg import eigsh, LinearOperator
import amm
from amm import geometry as G, fem, bloch, homog
from amm.pardiso import Pardiso

def bands_at(mesh, k, nev=10):
    K = mesh.assemble("K", k); M = mesh.assemble("M", k)
    R = lambda A: sp.bmat([[A.real, -A.imag], [A.imag, A.real]]).tocsr()
    Kr, Mr = R(K), R(M); s0 = -1e-3
    P = Pardiso(mtype=-2); P.factor(sp.triu(Kr - s0 * Mr, format="csr"))
    w = eigsh(Kr, k=2 * nev, M=Mr, sigma=s0, OPinv=LinearOperator(Kr.shape, matvec=P.solve, dtype=float),
              which="LM", return_eigenvectors=False)
    P.free()
    return np.sqrt(np.clip(np.sort(w)[::2], 0, None)) / (2 * np.pi * bloch.c_t())

ks = np.vstack([bloch.kpath(1)[0], bloch.ibz_interior(2, 3)])
for params in (dict(c=0.6, w=0.2), dict(c=0.57, w=0.17)):
    spec = dict(family="resonator", kind="cube_bars", params=params)
    for n in (10, 12, 16, 20, 24, 30):
        t = time.perf_counter()
        cov, sub, _ = G.design_cell(spec, n); mesh = fem.build_mesh(cov, sub=sub)
        r = homog.homogenize(mesh=mesh)
        f = np.array([bands_at(mesh, k) for k in ks])
        print(f"{params} n={n:2d} rho={r['density']:.4f} E100={r['E100']:.5f} G={r['G']:.5f} "
              f"band6max={f[:,5].max():.4f} band7min={f[:,6].min():.4f} ({time.perf_counter()-t:.1f}s)", flush=True)
