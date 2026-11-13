"""Gap-edge convergence vs resolution and element type (cube_bars c=0.6 w=0.2). Shift-invert Lanczos with PARDISO."""
import sys, time, numpy as np, scipy.sparse as sp
from scipy.sparse.linalg import eigsh, LinearOperator
import amm
from amm import geometry as G, fem, bloch
from amm.pardiso import Pardiso

def bands_at(mesh, k, nev=10, el="hex8i"):
    ke, me = fem.hex8_ke(mesh.h, fem.elastic_D(), el), fem.hex8_me(mesh.h)
    K = mesh.assemble(ke, k); M = mesh.assemble(me, k)
    R = lambda A: sp.bmat([[A.real, -A.imag], [A.imag, A.real]]).tocsr()
    Kr, Mr = R(K), R(M); s0 = -1e-3
    P = Pardiso(mtype=-2); P.factor(sp.triu(Kr + (-s0) * Mr * 0 + s0 * 0 * Mr - s0 * Mr, format="csr"))
    op = LinearOperator(Kr.shape, matvec=lambda x: P.solve(x), dtype=float)
    w = eigsh(Kr, k=2 * nev, M=Mr, sigma=s0, OPinv=op, which="LM", return_eigenvectors=False)
    P.free()
    w = np.sort(w)[::2]
    return np.sqrt(np.clip(w, 0, None)) / (2 * np.pi * bloch.c_t())

ks = np.vstack([bloch.kpath(1)[0], bloch.ibz_interior(2, 3)])
for el in ("hex8", "hex8i"):
    for n in (10, 16, 20, 24, 30):
        t = time.perf_counter()
        mesh = fem.build_mesh(G.clean(G.resonator("cube_bars", n, c=0.6, w=0.2))[0])
        f = np.array([bands_at(mesh, k, el=el) for k in ks])
        print(f"{el:5s} n={n:2d} band6max={f[:,5].max():.4f} band7min={f[:,6].min():.4f}  ({time.perf_counter()-t:.1f}s)", flush=True)
