"""Derived quantities of a homogenized stiffness tensor C* (6x6 Voigt, engineering shear in the order yz, xz, xy, as
amm.homog returns it). Pure functions of C*; used to report the full tensor in `evaluate` (plan B1).

Directional Young's modulus: 1/E(n) = n_i n_j n_k n_l S_ijkl with S the compliance tensor. In Voigt notation with
engineering shear strains, S_voigt = inv(C_voigt) and 1/E(n) = m^T S_voigt m with m = (n1^2, n2^2, n3^2, n2 n3,
n1 n3, n1 n2) (the shear rows of S_voigt already carry the factor of the engineering strain). For a cubic tensor the
extremes of E(n) lie along <100> and <111>; E110 is reported as well.
"""
from __future__ import annotations

import numpy as np

VOIGT_ORDER = "11, 22, 33, 23 (yz), 13 (xz), 12 (xy); engineering shear strains"


def _m(n) -> np.ndarray:
    n = np.asarray(n, float)
    n = n / np.linalg.norm(n)
    return np.array([n[0] ** 2, n[1] ** 2, n[2] ** 2, n[1] * n[2], n[0] * n[2], n[0] * n[1]])


def directional_young(C, n) -> float:
    S = np.linalg.inv(np.asarray(C, float))
    m = _m(n)
    return float(1.0 / (m @ S @ m))


def summary(C) -> dict:
    """Tensor-derived quantities (same normalization as C*, i.e. by E_s): directional Young's moduli along [100],
    [110], [111] from the full tensor, compliance-based Poisson ratio nu12, Voigt and Reuss bulk and shear averages,
    eigenvalues of C* (positive definite = stable)."""
    C = np.asarray(C, float)
    S = np.linalg.inv(C)
    eig = np.linalg.eigvalsh(0.5 * (C + C.T))
    KV = float((C[0, 0] + C[1, 1] + C[2, 2] + 2 * (C[0, 1] + C[0, 2] + C[1, 2])) / 9)
    GV = float((C[0, 0] + C[1, 1] + C[2, 2] - (C[0, 1] + C[0, 2] + C[1, 2]) + 3 * (C[3, 3] + C[4, 4] + C[5, 5])) / 15)
    KR = float(1 / (S[0, 0] + S[1, 1] + S[2, 2] + 2 * (S[0, 1] + S[0, 2] + S[1, 2])))
    GR = float(15 / (4 * (S[0, 0] + S[1, 1] + S[2, 2]) - 4 * (S[0, 1] + S[0, 2] + S[1, 2])
                     + 3 * (S[3, 3] + S[4, 4] + S[5, 5])))
    return dict(E100=directional_young(C, (1, 0, 0)), E110=directional_young(C, (1, 1, 0)),
                E111=directional_young(C, (1, 1, 1)), nu12=float(-S[0, 1] / S[0, 0]),
                bulk_voigt=KV, bulk_reuss=KR, shear_voigt=GV, shear_reuss=GR,
                eigenvalues=[float(x) for x in eig])
