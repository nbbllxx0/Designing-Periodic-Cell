"""Periodic homogenization of a voxel cell: effective stiffness C* (6x6, Voigt, engineering shear yz, xz, xy).

Same formulation as the energy form of the registry code (arXiv 2609.14741), re-implemented independently here:
void voxels are removed, the cell must be one periodically face-connected component (`geometry.clean`), the three
rigid translations are removed by pinning one node, and K chi_m = F_m is solved for the six unit strains with one
FP64 sparse Cholesky factorization (PARDISO, mtype 2). Then

    C*_mn = (1/V) sum_e (chi0_m - chi_m)_e^T  k_e  (chi0_n - chi_n)_e,   V = 1.

The certificate records the FP64 relative residual of each load case, the asymmetry of C*, and its smallest
eigenvalue.
"""
from __future__ import annotations

import time

import numpy as np
import scipy.sparse as sp

from . import fem
from .pardiso import Pardiso

STRAINS = [np.diag([1.0, 0, 0]), np.diag([0, 1.0, 0]), np.diag([0, 0, 1.0]),
           np.array([[0, 0, 0], [0, 0, .5], [0, .5, 0]]),
           np.array([[0, 0, .5], [0, 0, 0], [.5, 0, 0]]),
           np.array([[0, .5, 0], [.5, 0, 0], [0, 0, 0]])]


def homogenize(mask: np.ndarray | None = None, nu: float = 0.3, mesh: fem.CellMesh | None = None,
               sub: np.ndarray | None = None) -> dict:
    """mask: bool voxels or float coverage; sub: sub-samples for finite-cell partial voxels; or a prebuilt mesh."""
    t0 = time.perf_counter()
    mesh = mesh or fem.build_mesh(mask, sub=sub, nu=nu)
    h = mesh.h
    K = mesh.assemble("K")  # real, full CSR
    N = mesh.ndof
    xloc = fem.OFF * h
    chi0 = np.stack([(xloc @ e.T).ravel() for e in STRAINS])  # (6,24)
    fe = np.einsum("eij,mj->mei", mesh.Ke, chi0)  # (6,ne,24)
    F = np.zeros((N, 6))
    for m in range(6):
        F[:, m] = np.bincount(mesh.edof.ravel(), weights=fe[m].ravel(), minlength=N)
    keep = np.arange(3, N)  # pin node 0 (removes the 3 rigid translations of a connected periodic cell)
    Kr = K[keep][:, keep].tocsr()
    U = sp.triu(Kr, format="csr")
    U.sort_indices()
    solver = Pardiso(mtype=2)
    st = solver.factor(U)
    X = np.zeros((N, 6))
    X[keep] = solver.solve(F[keep])
    solver.free()
    res = np.linalg.norm(Kr @ X[keep] - F[keep], axis=0) / np.maximum(np.linalg.norm(F[keep], axis=0), 1e-300)
    De = chi0[:, None, :] - X[mesh.edof].transpose(2, 0, 1)  # (6,ne,24)
    KD = np.einsum("mei,eij->mej", De, mesh.Ke)  # (6,ne,24)
    C = np.einsum("men,pen->mp", KD, De)  # V = 1
    asym = float(np.linalg.norm(C - C.T) / np.linalg.norm(C))
    C = 0.5 * (C + C.T)
    eig = np.linalg.eigvalsh(C)
    return dict(C=C, residual=res.tolist(), max_residual=float(res.max()), asymmetry=asym, min_eig=float(eig[0]),
                ndof=N, density=mesh.density, factor_perturbed=st["n_perturbed"],
                seconds=round(time.perf_counter() - t0, 3), **cubic_constants(C))


def cubic_constants(C: np.ndarray) -> dict:
    """Engineering constants (normalized by E_s). Cubic averages plus a symmetry-deviation measure."""
    C11 = float(np.mean(np.diag(C)[:3]))
    C12 = float(np.mean([C[0, 1], C[0, 2], C[1, 2]]))
    C44 = float(np.mean(np.diag(C)[3:]))
    Cc = np.zeros((6, 6))
    Cc[:3, :3] = C12
    Cc[np.arange(3), np.arange(3)] = C11
    Cc[3:, 3:] = np.eye(3) * C44
    dev = float(np.linalg.norm(C - Cc) / np.linalg.norm(C))
    S = np.linalg.inv(C)
    E1 = 1.0 / S[0, 0]
    nu12 = -S[0, 1] / S[0, 0]
    zener = 2 * C44 / (C11 - C12) if abs(C11 - C12) > 1e-15 else np.inf
    return dict(C11=C11, C12=C12, C44=C44, E100=float(E1), nu100=float(nu12), G=C44, bulk=(C11 + 2 * C12) / 3,
                zener=float(zener), cubic_deviation=dev)
