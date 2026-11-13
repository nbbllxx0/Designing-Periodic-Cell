"""Third-party FE check with scikit-fem (installed 2026-11-06 with the user's approval). Nothing from amm except the
voxelized design (amm.geometry) and the certificates being tested; nothing from indep_fe except the element matrices
being compared in part 1.

1. Element: scikit-fem's 27-node hex (ElementHex2) stiffness and mass on a unit cube vs indep_fe.element_matrices
   (eigenvalues, invariant to the node ordering).
2. Cells: homogenization in scikit-fem alone, with kinematic uniform boundary conditions (u = E x on the six cell
   faces; void surfaces traction free). For a conforming model, C_KUBC(FE) >= C_KUBC(exact) >= C_periodic(exact) in
   the Loewner order, so E100 = 1/S11, G = C44 and bulk are rigorous UPPER bounds of the exact periodic values.
   Test: amm certified lower bound <= scikit-fem KUBC value. (Looser than the periodic Q2 check, fully third-party.)

    skfem_check.py [n]   -> results/verification/skfem/summary.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import indep_fe  # noqa: E402
import run_indep  # noqa: E402
from amm import geometry  # noqa: E402

import skfem  # noqa: E402
from skfem import Basis, BilinearForm, ElementHex2, ElementVector, MeshHex, asm, condense  # noqa: E402
from skfem.helpers import ddot, dot, sym_grad, trace, eye  # noqa: E402

OUT = ROOT / "results" / "verification" / "skfem"
INTORDER = 5  # 3-point Gauss per direction: exact for the Q2 stiffness and mass (degree <= 4 per direction)


def forms(nu):
    lam, mu = nu / ((1 + nu) * (1 - 2 * nu)), 1 / (2 * (1 + nu))

    @BilinearForm
    def stiff(u, v, w):
        e = sym_grad(u)
        return ddot(2 * mu * e + lam * eye(trace(e), 3), sym_grad(v))

    @BilinearForm
    def mass(u, v, w):
        return dot(u, v)
    return stiff, mass


def element_check(nu=0.3):
    m = MeshHex()  # unit cube, one element
    b = Basis(m, ElementVector(ElementHex2()), intorder=INTORDER)
    stiff, mass = forms(nu)
    K, M = asm(stiff, b).toarray(), asm(mass, b).toarray()
    Ke, Me = indep_fe.element_matrices(1.0, nu)
    ek, ei = np.sort(np.linalg.eigvalsh(K)), np.sort(np.linalg.eigvalsh(Ke))
    mk, mi = np.sort(np.linalg.eigvalsh(M)), np.sort(np.linalg.eigvalsh(Me))
    return dict(nu=nu, n_dofs=K.shape[0], stiffness_eig_max_abs_diff=float(np.abs(ek - ei).max()),
                stiffness_eig_max=float(ek.max()), mass_eig_max_abs_diff=float(np.abs(mk - mi).max()),
                mass_eig_max=float(mk.max()), skfem=skfem.__version__)


def kubc(solid: np.ndarray, nu: float) -> dict:
    from pypardiso import spsolve
    n = solid.shape[0]
    g = np.linspace(0, 1, n + 1)
    mesh = MeshHex.init_tensor(g, g, g)
    mid = mesh.p[:, mesh.t].mean(axis=1)  # (3, ne)
    idx = np.clip(np.floor(mid * n).astype(int), 0, n - 1)
    keep = np.nonzero(solid[idx[0], idx[1], idx[2]] > 0.5)[0]
    mesh = mesh.restrict(keep)
    b = Basis(mesh, ElementVector(ElementHex2()), intorder=INTORDER)
    stiff, _ = forms(nu)
    K = asm(stiff, b).tocsr()
    on_face = lambda x: (np.isclose(x[0], 0) | np.isclose(x[0], 1) | np.isclose(x[1], 0) | np.isclose(x[1], 1)
                         | np.isclose(x[2], 0) | np.isclose(x[2], 1))
    D = b.get_dofs(on_face).all()
    U = []
    for c in range(6):
        e = np.eye(6)[c]
        E = np.array([[e[0], e[5] / 2, e[4] / 2], [e[5] / 2, e[1], e[3] / 2], [e[4] / 2, e[3] / 2, e[2]]])
        u0 = np.zeros(b.N)  # nodal interpolation of the affine field (exact: affine fields are in the space)
        for comp, ix in enumerate(b.split_indices()):
            u0[ix] = (E @ b.doflocs[:, ix])[comp]
        A, rhs, x, I = condense(K, np.zeros(K.shape[0]), x=u0, D=D)
        x = x.copy()
        x[I] = spsolve(A.tocsr(), rhs)
        U.append(x)
    U = np.stack(U, axis=1)
    C = U.T @ (K @ U)  # cell volume 1
    C = (C + C.T) / 2
    S = np.linalg.inv(C)
    return dict(C=C.tolist(), E100=float(1 / S[0, 0]), G=float(C[3, 3]), bulk=float((C[0, 0] + 2 * C[0, 1]) / 3),
                n_dofs=int(K.shape[0]), n_fixed=int(len(D)), density=float(len(keep) / n ** 3), n=n, bc="KUBC")


def main(n=20):
    OUT.mkdir(parents=True, exist_ok=True)
    out = dict(element=[element_check(nu) for nu in run_indep.NUS])
    full = kubc(np.ones((4, 4, 4)), 0.3)  # homogeneous solid: KUBC is exact, C must equal D
    out["homogeneous_C_error"] = float(np.abs(np.array(full["C"]) - indep_fe.iso_D(0.3)).max())
    rows = []
    out["missing"] = []
    for cell in run_indep.cells():
        if not (run_indep.OUT / f"{cell['name']}_amm.json").exists():
            out["missing"].append(cell["name"])
            continue
        a = json.loads((run_indep.OUT / f"{cell['name']}_amm.json").read_text(encoding="utf-8"))
        q = a["blocks"]["static"]["convergence"]["quantities"]
        cov, _, _ = geometry.design_cell(cell["spec"], n)
        assert set(map(float, set(cov.ravel().round(9)))) <= {0.0, 1.0}, "voxelization not exact"
        t0 = time.perf_counter()
        r = kubc(cov, cell["nu"])
        chk = {k: dict(amm_lower=q[k]["lower"], skfem_kubc_upper_bound=r[k],
                       necessary_check_passed=bool(q[k]["lower"] <= r[k] * (1 + 1e-9))) for k in ("E100", "G", "bulk")}
        qf = run_indep.OUT / f"{cell['name']}_q2_n{n}.json"
        if qf.exists():  # same Q2 space, KUBC is the more constrained problem: must be >= the periodic Q2 value
            st = json.loads(qf.read_text(encoding="utf-8"))["static"]
            for k in ("E100", "G", "bulk"):
                chk[k]["indep_periodic_q2"] = st[k]
                chk[k]["kubc_ge_periodic"] = bool(r[k] >= st[k] * (1 - 1e-9))
        rows.append(dict(name=cell["name"], nu=cell["nu"], amm_verdict=a["verdict"], checker=a.get("checker"), n=n,
                         n_dofs=r["n_dofs"], seconds=round(time.perf_counter() - t0, 1), static=chk))
        print(cell["name"], " ".join(f"{k}:{'ok' if c['necessary_check_passed'] else 'FAIL'}"
                                     f"({c['amm_lower']:.4g}<={c['skfem_kubc_upper_bound']:.4g})"
                                     for k, c in chk.items()), rows[-1]["seconds"], "s", flush=True)
    out["rows"] = rows
    out["n_checks"] = 3 * len(rows)
    out["n_passed"] = sum(c["necessary_check_passed"] for r in rows for c in r["static"].values())
    out["kubc_ge_periodic"] = [sum(c.get("kubc_ge_periodic", False) for r in rows for c in r["static"].values()),
                               sum("kubc_ge_periodic" in c for r in rows for c in r["static"].values())]
    (OUT / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
