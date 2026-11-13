"""V1c host side: amm's own Bloch bands at given k, from the FROZEN E4 code, under the shared solver lock.

Models:
  cert  the certificate's discretization: certify._mesh(spec, n, nu) = geometry.design_cell + fem.build_mesh with
        finite-cell partial voxels and the default element (hex8i for full voxels, trilinear finite-cell partial ones)
  id    the identity model for DOLFINx Q1: fem.build_mesh(cov, sub, nu, element="hex8") (trilinear everywhere,
        exact integration on full voxels, midpoint rule on the s^3 sub-cubes of partial voxels)
K(k) and M(k) are amm's own assembly (CellMesh.assemble, Floquet phases on wrapped nodes). Eigenvalues: block
subspace iteration with a complex sparse LU of K - sigma M (sigma = -1e-2), Rayleigh-Ritz on a block of nev + 12
vectors until every relative residual is <= 1e-10 (a single-vector Lanczos can miss copies of degenerate
eigenvalues, which would shift band indices).

Usage: python scripts/verify/dolfinx/amm_bands.py <case> <model> <n> [ks.json]   (default ks: the case's 37 k)
Output: results/verification/dolfinx/amm/<case>_<model>_n<n>[_<tag>].json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import scipy.linalg as sla
import scipy.sparse.linalg as spla

ROOT = Path(__file__).resolve().parents[3]
FROZEN = Path(r"C:\AI\AgenticMetamaterials_workspaces\v1c_frozen")
sys.path.insert(0, str(FROZEN))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from amm import bloch, certify, fem, geometry  # noqa: E402
from lock import GpuLock  # noqa: E402

assert Path(certify.__file__).resolve().is_relative_to(FROZEN)
assert certify.checker_hash() == "f2e482d81382b400"
INP = ROOT / "results/verification/dolfinx/inputs"
OUT = ROOT / "results/verification/dolfinx/amm"


def subspace_eigs(K, M, nev, sigma=-1e-2, extra=12, rtol=1e-10, maxit=600, seed=0):
    """Block shift-invert subspace iteration; stops when every relative residual |K x - lam M x| / |K x| of the nev
    lowest Ritz pairs (rigid-body modes, |lam| < 1e-9, excluded) is <= rtol, or on stagnation below 1e-8."""
    N = K.shape[0]
    lu = spla.splu((K - sigma * M).tocsc().astype(complex))
    rng = np.random.default_rng(seed)
    p = nev + extra
    X = rng.standard_normal((N, p)) + 1j * rng.standard_normal((N, p))
    hist = []
    for it in range(maxit):
        Y = lu.solve(M @ X)
        A, B = Y.conj().T @ (K @ Y), Y.conj().T @ (M @ Y)
        A, B = 0.5 * (A + A.conj().T), 0.5 * (B + B.conj().T)
        w, V = sla.eigh(A, B)
        X = Y @ V
        X /= np.linalg.norm(X, axis=0)
        KX = K @ X[:, :nev]
        R = KX - (M @ X[:, :nev]) * w[None, :nev]
        res = np.linalg.norm(R, axis=0) / np.maximum(np.linalg.norm(KX, axis=0), 1e-300)
        rmax = float(np.max(np.where(np.abs(w[:nev]) < 1e-9, 0.0, res)))
        hist.append(rmax)
        if rmax <= rtol or (len(hist) > 8 and rmax <= 1e-8 and rmax > 0.7 * hist[-5]):
            break
    return w[:nev], res, it + 1


def main():
    name, model, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    case = json.load(open(INP / f"{name}.json"))
    if len(sys.argv) > 4:
        ks = np.asarray(json.load(open(sys.argv[4])), float).reshape(-1, 3)
        tag = "_" + Path(sys.argv[4]).stem
    else:
        ks = np.vstack([case["ks"]["path"], case["ks"]["interior"], case["ks"]["adversarial"]])
        tag = ""
    nu, nb = case["nu"], case["below_band"]
    nev = nb + 4
    if model == "cert":
        mesh, info = certify._mesh(case["spec"], n, nu)
    else:
        cov, sub, info = geometry.design_cell(case["spec"], n)
        mesh = fem.build_mesh(cov, sub=sub, nu=nu, element="hex8")
    ct = bloch.c_t(nu=nu)
    recs = []
    with GpuLock(f"V1c amm_bands {name} {model} n{n}"):
        t0 = time.perf_counter()
        for k in ks:
            t1 = time.perf_counter()
            K, M = mesh.assemble("K", k), mesh.assemble("M", k)
            w, res, it = subspace_eigs(K, M, nev)
            recs.append(dict(k=k.tolist(), f=(np.sqrt(np.clip(w, 0, None)) / (2 * np.pi * ct)).tolist(),
                             lam=w.tolist(), rel_res=res.tolist(), iters=it, seconds=round(time.perf_counter() - t1, 2)))
            print(name, model, n, np.round(k / np.pi, 4).tolist(), np.round(recs[-1]["f"][nb - 1:nb + 1], 6), it,
                  flush=True)
        sec = round(time.perf_counter() - t0, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    out = dict(case=name, model=model, n=n, element=fem.ELEMENT if model == "cert" else "hex8",
               ndof=int(mesh.ndof), density=float(mesh.density), checker=certify.checker_hash(), nev=nev,
               below_band=nb, records=recs, seconds=sec)
    p = OUT / f"{name}_{model}_n{n}{tag}.json"
    json.dump(out, open(p, "w"), indent=1)
    print("wrote", p, sec, "s")


if __name__ == "__main__":
    main()
