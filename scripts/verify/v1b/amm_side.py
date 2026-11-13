"""V1b: amm's own certificate-tier model (amm.fem hex8i + finite-cell partial voxels, amm.bloch inertia counts and
Lanczos edges, phase 0) at the k-points of the independent run, so that per-k values can be compared.

    amm_side.py <cell id>     -> results/verification/v1b/<id>_amm_k.json   (needs q2/<id>_bloch.json)

Gap cells: at each k, the count below the claim centre (inertia of amm's real 2N matrix) and the eigenvalues just
below / above it. No-gap cells: the lowest 15 eigenvalues. Resolutions: n = 20 at every k of the independent
level-1 set; n = 30 and 40 at the independent refinement subset (cost: about 5-40 s per k and resolution).
CPU only (no GPU), MKL threads from the environment.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MKL_NUM_THREADS", "6")
os.environ.setdefault("OMP_NUM_THREADS", "6")
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
from amm import bloch, certify  # noqa: E402
from amm.pardiso import Pardiso  # noqa: E402

OUT = ROOT / "results" / "verification" / "v1b"
PI = np.pi


class AmmModel:
    """amm's assembled K(k), M(k) (amm.fem) and amm's PARDISO wrapper on amm's real 2N form; one solver per mesh
    (symbolic factorization reused). The eigen driver (scipy eigsh, shift-invert, 8 eigenvalues, tol 1e-9) is the
    same as on the Q2 side; amm's own InertiaCounter.edge (nev = 3) was too slow for 50 k-points per resolution."""

    def __init__(self, mesh):
        self.mesh, self.ps, self.N = mesh, Pardiso(mtype=-2), mesh.ndof

    def near(self, k, fc, nev=8, sigma=None):
        from scipy.sparse.linalg import LinearOperator, eigsh
        m, N = self.mesh, self.N
        Kd = m.csr_data(m.element_values("K", k)).astype(complex)
        Md = m.csr_data(m.element_values("M", k)).astype(complex)
        s = bloch.f_to_sigma(fc, m.nu) if sigma is None else sigma
        st = self.ps.factor(m.real2n_upper(Kd - s * Md))
        K = sp.csr_matrix((Kd, m.indices, m.indptr), shape=(N, N))
        M = sp.csr_matrix((Md, m.indices, m.indptr), shape=(N, N))

        def inv(x):
            x = np.asarray(x).ravel()
            y = self.ps.solve(np.concatenate([x.real, x.imag]))
            return y[:N] + 1j * y[N:]
        v0 = np.random.default_rng(7).standard_normal(N) + 0j
        while True:
            w = eigsh(K, k=nev, M=M, sigma=s, OPinv=LinearOperator((N, N), matvec=inv, dtype=complex), which="LM",
                      return_eigenvectors=False, tol=1e-9, v0=v0)
            f = np.sort(np.sqrt(np.clip(np.real(w), 0, None)) / (2 * PI * bloch.c_t(nu=m.nu)))
            if sigma is not None or ((f < fc).any() and (f >= fc).any()) or nev >= 32:
                break
            nev = min(2 * nev, 32)
        return f, st["n_neg"] // 2, st["n_perturbed"]

    def free(self):
        self.ps.free()


def lowest(model, k, nev=15):
    f, _, _ = model.near(k, 0.0, nev=nev, sigma=-bloch.f_to_sigma(0.01, model.mesh.nu))
    return f.tolist()


def main(cid):
    cells = {c["id"]: c for c in json.loads((OUT / "cells.json").read_text(encoding="utf-8"))["cells"]}
    cell = cells[cid]
    q = json.loads((OUT / "q2" / f"{cid}_bloch.json").read_text(encoding="utf-8"))
    lv = [str(n) for n in q["levels"]]
    rows1 = q["levels_data"][lv[0]]["rows"]
    sub_keys = {(r["set"], r["i"]) for r in q["levels_data"][lv[1]]["rows"]}
    t0 = time.perf_counter()
    out = dict(id=cid, kind=q["kind"], checker=certify.checker_hash(), levels={})
    for n in (20, 30, 40):
        t1 = time.perf_counter()
        mesh, info = certify._mesh(cell["spec"], n, cell["nu"])
        am = AmmModel(mesh)
        rows = []
        for r in rows1:
            key = (r["set"], r["i"])
            if n in (30, 40) and key not in sub_keys:  # n = 20: every level-1 k; n = 30, 40: refinement subset
                continue
            k = np.array(r["k"]) * PI
            if q["kind"] == "gap":
                fc = q["f_center"]
                f, nbk, pert = am.near(k, fc)
                lo = float(f[f < fc].max()) if (f < fc).any() else None
                hi = float(f[f >= fc].min()) if (f >= fc).any() else None
                rows.append(dict(set=r["set"], i=r["i"], k=r["k"], n_below=int(nbk), perturbed=int(pert),
                                 below_fc=lo, above_fc=hi, f=f.tolist()))
            else:
                rows.append(dict(set=r["set"], i=r["i"], k=r["k"], f=lowest(am, k)))
        am.free()
        out["levels"][str(n)] = dict(rows=rows, ndof=mesh.ndof, density=mesh.density,
                                     seconds=round(time.perf_counter() - t1, 1))
        print(cid, "amm n", n, len(rows), "k", round(time.perf_counter() - t1, 1), "s", flush=True)
    out["seconds"] = round(time.perf_counter() - t0, 1)
    (OUT / f"{cid}_amm_k.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
