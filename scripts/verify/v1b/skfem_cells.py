"""V1b semi-independent static check with scikit-fem (12.0.2): ElementHex2 assembly on the cut-cell tensor mesh,
scikit-fem quadrature (full voxels: 3^3 Gauss, intorder 5; cut voxels: 2^3 sub-cubes x 3^3 Gauss points with the
SHARP solid indicator evaluated at scikit-fem global quadrature coordinates, void floor 1e-6), then
  * periodic homogenization through a node-identification matrix P (written here): K_p = P^T K P, fluctuation
    solve with one node pinned, C = (u0 + P u)^T K (u0 + P u);
  * KUBC: u = E x on the six cell faces (void surfaces traction free).
Geometry: the design evaluator of q2fcm.Design (shared with Q2-FCM, not with amm). No amm import.

    skfem_cells.py [n ...]   -> results/verification/v1b/skfem/<id>_n<n>.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MKL_NUM_THREADS", "12")
os.environ.setdefault("OMP_NUM_THREADS", "12")
import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q2fcm  # noqa: E402
import skfem  # noqa: E402
from skfem import Basis, BilinearForm, ElementHex2, ElementVector, MeshHex, asm, condense  # noqa: E402
from skfem.helpers import ddot, eye, sym_grad, trace  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v1b"
ALPHA = 1e-6


def composite_rule(s=3):
    g = 0.5 + 0.5 * np.array([-np.sqrt(0.6), 0.0, np.sqrt(0.6)])
    wg = np.array([5 / 18, 8 / 18, 5 / 18])
    p1 = ((np.arange(s)[:, None] + g[None, :]) / s).ravel()
    w1 = np.tile(wg, s) / s
    X = np.stack(np.meshgrid(p1, p1, p1, indexing="ij"), 0).reshape(3, -1)
    W = np.einsum("i,j,k->ijk", w1, w1, w1).ravel()
    return X, W


def build(design, n, nu):
    g = np.linspace(0, 1, n + 1)
    mesh = MeshHex.init_tensor(g, g, g)
    ctr = mesh.p[:, mesh.t].mean(axis=1).T  # (ne, 3)
    ph = design.phi(ctr)
    hd = np.sqrt(3) / (2 * n)
    full = ph < -design.lip * hd
    void = ph > design.lip * hd
    cut = np.flatnonzero(~(full | void))
    Xr, Wr = composite_rule(2)
    lo = mesh.p[:, mesh.t].min(axis=1).T  # (ne, 3) lower corner
    pts = lo[cut][:, None, :] + Xr.T[None, :, :] / n
    chi = (design.phi(pts) <= 0)
    frac = chi.astype(float) @ Wr
    full[cut[chi.all(axis=1)]] = True
    keep_cut = cut[(frac > 0) & ~chi.all(axis=1)]
    keep = np.sort(np.concatenate([np.flatnonzero(full), keep_cut]))
    density = float(full.sum() + frac[np.isin(cut, keep_cut)].sum()) / n ** 3
    m = mesh.restrict(keep)
    # re-classify on the restricted mesh (element order of restrict)
    lo2 = m.p[:, m.t].min(axis=1).T
    idx = np.round(lo2 * n).astype(int)
    lin = (idx[:, 0] * n + idx[:, 1]) * n + idx[:, 2]
    lin0 = (np.round(lo * n).astype(int) @ np.array([n * n, n, 1]))
    is_full = np.isin(lin, lin0[full])
    e = ElementVector(ElementHex2())
    lam, mu = nu / ((1 + nu) * (1 - 2 * nu)), 1 / (2 * (1 + nu))

    @BilinearForm
    def stiff(u, v, w):
        eps = sym_grad(u)
        return ddot(2 * mu * eps + lam * eye(trace(eps), 3), sym_grad(v))

    @BilinearForm
    def stiff_chi(u, v, w):
        eps = sym_grad(u)
        return w.chi * ddot(2 * mu * eps + lam * eye(trace(eps), 3), sym_grad(v))

    bf = Basis(m, e, intorder=5, elements=np.flatnonzero(is_full))
    K = asm(stiff, bf)
    cid = np.flatnonzero(~is_full)
    if len(cid):
        bc = Basis(m, e, quadrature=(Xr, Wr), elements=cid)
        x = np.moveaxis(np.asarray(bc.global_coordinates().value), 0, -1)  # (nel, nqp, 3) quadrature points
        chi = np.where(design.phi(x) <= 0, 1.0, ALPHA)  # evaluated once (not once per basis pair)
        K = K + asm(stiff_chi, bc, chi=chi)
    return m, bf, K.tocsr(), density, int(len(cid))


def strain(c):
    e = np.eye(6)[c]
    return np.array([[e[0], e[5] / 2, e[4] / 2], [e[5] / 2, e[1], e[3] / 2], [e[4] / 2, e[3] / 2, e[2]]])


def constants(C):
    S = np.linalg.inv(C)
    C11 = float(np.mean(np.diag(C)[:3]))
    C12 = float(np.mean([C[0, 1], C[0, 2], C[1, 2]]))
    return dict(C=C.tolist(), C11=C11, C12=C12, C44=float(np.mean(np.diag(C)[3:])), G=float(np.mean(np.diag(C)[3:])),
                E100=float(np.mean(1 / np.diag(S)[:3])), bulk=(C11 + 2 * C12) / 3,
                nu100=float(np.mean([-S[0, 1] / S[0, 0], -S[0, 2] / S[0, 0], -S[1, 2] / S[1, 1]])))


def solve(A, b):
    from pypardiso import spsolve
    return spsolve(A.tocsr(), b)


def periodic(b, K, n):
    N = K.shape[0]
    X = b.doflocs  # (3, N)
    comp = np.zeros(N, int)
    for c, ix in enumerate(b.split_indices()):
        comp[ix] = c
    key = np.round(np.mod(X, 1.0) * 2 * n).astype(np.int64) % (2 * n)
    lin = ((key[0] * 2 * n + key[1]) * 2 * n + key[2]) * 3 + comp
    u, inv = np.unique(lin, return_inverse=True)
    P = sp.csr_matrix((np.ones(N), (np.arange(N), inv)), shape=(N, len(u)))
    Kp = (P.T @ K @ P).tocsr()
    U0 = np.stack([(strain(c) @ X)[comp, np.arange(N)] for c in range(6)], axis=1)
    F = -(P.T @ (K @ U0))
    node0 = lin[0] // 3
    pin = np.flatnonzero(u // 3 == node0)
    free = np.setdiff1d(np.arange(len(u)), pin)
    Uf = np.zeros((len(u), 6))
    Uf[free] = solve(Kp[free][:, free], F[free])
    res = float(np.abs(Kp[free][:, free] @ Uf[free] - F[free]).max() / np.abs(F).max())
    T = U0 + P @ Uf
    C = T.T @ (K @ T)
    return dict(constants(0.5 * (C + C.T)), residual=res, n_dofs=int(len(u)))


def kubc(b, K):
    X = b.doflocs
    on = lambda x: (np.isclose(x[0], 0) | np.isclose(x[0], 1) | np.isclose(x[1], 0) | np.isclose(x[1], 1)
                    | np.isclose(x[2], 0) | np.isclose(x[2], 1))
    D = b.get_dofs(on).all()
    U = []
    for c in range(6):
        u0 = np.zeros(b.N)
        for comp, ix in enumerate(b.split_indices()):
            u0[ix] = (strain(c) @ X[:, ix])[comp]
        A, rhs, x, I = condense(K, np.zeros(K.shape[0]), x=u0, D=D)
        x = x.copy()
        x[I] = solve(A, rhs)
        U.append(x)
    U = np.stack(U, axis=1)
    C = U.T @ (K @ U)
    return dict(constants(0.5 * (C + C.T)), n_fixed=int(len(D)))


def main(ns):
    (OUT / "skfem").mkdir(parents=True, exist_ok=True)
    cells = json.loads((OUT / "cells.json").read_text(encoding="utf-8"))["cells"]
    for c in cells:
        d = q2fcm.Design(c["spec"])
        for n in ns:
            f = OUT / "skfem" / f"{c['id']}_n{n}.json"
            if f.exists():
                continue
            t0 = time.perf_counter()
            m, b, K, rho, ncut = build(d, n, c["nu"])
            r = dict(id=c["id"], n=n, nu=c["nu"], density=rho, n_cut=ncut, n_elements=int(m.t.shape[1]),
                     n_dofs_full=int(K.shape[0]), skfem=skfem.__version__)
            r["periodic"] = periodic(b, K, n)
            r["kubc"] = kubc(b, K)
            r["wall_s"] = round(time.perf_counter() - t0, 1)
            f.write_text(json.dumps(r, indent=1), encoding="utf-8")
            print(c["id"], n, "per", {k: round(r["periodic"][k], 6) for k in ("E100", "G", "bulk")},
                  "kubc", {k: round(r["kubc"][k], 6) for k in ("E100", "G", "bulk")}, r["wall_s"], "s", flush=True)


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or [12, 16])
