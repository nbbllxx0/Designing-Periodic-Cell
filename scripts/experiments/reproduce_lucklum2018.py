"""Reproduce Lucklum & Vellekoop, Appl. Phys. Lett. 113, 201902 (2018), doi:10.1063/1.5049663.

Simple cubic cell, spheres at the corners joined by beams along the cube edges = (shifted by a/2) our families
sphere_ligaments (sphere radius c, ligament diameter w) and cube_bars (cube edge c, square bar width w).
Material: E = 3.2 GPa, rho = 1190 kg/m^3, c_l = 2077.5 m/s  =>  nu = 0.350 (derived; paper does not print nu).
Reported (text, p. 201902-2): first gap f a / c_l = 0.0437 .. 0.4702 (166.0 %); X-point modes 0.008, 0.016, 0.042,
0.470 (Fig. 3 caption); variants: ball 0.78a / beam 0.1a 137.4 %, cube 0.7a / square beam 0.1a 125.3 %.
Bands by shift-invert Lanczos with PARDISO on the real 2N form, finite-cell partial voxels (amm).
"""
import json, sys, time
import numpy as np, scipy.sparse as sp
from scipy.sparse.linalg import eigsh, LinearOperator
import amm
from amm import bloch, fem, geometry as G
from amm.pardiso import Pardiso

NU = 0.35
CL_OVER_CT = np.sqrt(2 * (1 - NU) / (1 - 2 * NU))  # 2.0817
CASES = {
    "ball079_beam005": dict(spec=dict(family="resonator", kind="sphere_ligaments", params=dict(c=0.395, w=0.05)),
                            paper=dict(lo=0.0437, hi=0.4702, ratio=1.660, X=[0.008, 0.016, 0.042, 0.470])),
    "ball078_beam010": dict(spec=dict(family="resonator", kind="sphere_ligaments", params=dict(c=0.39, w=0.10)),
                            paper=dict(ratio=1.374)),
    "cube070_bar010": dict(spec=dict(family="resonator", kind="cube_bars", params=dict(c=0.70, w=0.10)),
                           paper=dict(ratio=1.253)),
}


def bands_at(mesh, k, nev):
    K, M = mesh.assemble("K", k), mesh.assemble("M", k)
    R = lambda A: sp.bmat([[A.real, -A.imag], [A.imag, A.real]]).tocsr()
    Kr, Mr = R(K), R(M)
    s0 = -1e-4
    P = Pardiso(mtype=-2)
    P.factor(sp.triu(Kr - s0 * Mr, format="csr"))
    w = eigsh(Kr, k=2 * nev, M=Mr, sigma=s0, OPinv=LinearOperator(Kr.shape, matvec=P.solve, dtype=float),
              which="LM", return_eigenvectors=False, tol=1e-10)
    P.free()
    return np.sqrt(np.clip(np.sort(w)[::2], 0, None)) / (2 * np.pi * bloch.c_t(nu=NU))  # f* = f a / c_t


if __name__ == "__main__":
    case, ns = sys.argv[1], [int(x) for x in sys.argv[2].split(",")]
    c = CASES[case]
    ks = np.vstack([bloch.kpath(4)[0], bloch.ibz_interior(6, 7)])
    out = []
    for n in ns:
        t = time.perf_counter()
        cov, sub, info = G.design_cell(c["spec"], n)
        mesh = fem.build_mesh(cov, sub=sub, nu=NU)
        f = np.array([bands_at(mesh, k, 10) for k in ks])  # f*
        fl = f / CL_OVER_CT  # f a / c_l, the paper's normalization
        gp = bloch.gaps(fl)
        X = fl[4]  # kpath(4): index 4 is X
        row = dict(case=case, n=n, ndof=mesh.ndof, density=info["density"], percolates=info["percolates"],
                   gaps_fa_over_cl=gp[:2], X_modes_fa_over_cl=np.round(X[:8], 4).tolist(),
                   seconds=round(time.perf_counter() - t, 1), paper=c["paper"])
        out.append(row)
        g0 = gp[0] if gp else None
        print(json.dumps(dict(case=case, n=n, ndof=mesh.ndof, rho=round(info["density"], 4),
                              gap=None if not g0 else dict(below=g0["below_band"], lo=round(g0["f_lo"], 4),
                                                           hi=round(g0["f_hi"], 4), ratio=round(g0["rel"], 4)),
                              X=row["X_modes_fa_over_cl"][:7], s=row["seconds"], paper=c["paper"])), flush=True)
    json.dump(out, open(f"results/verification/lucklum2018_{case}.json", "w"), indent=1, default=float)
