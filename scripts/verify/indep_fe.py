"""Independent FE check of the certificate (audit F06, 2026-11-06). Written separately from amm/fem.py, amm/homog.py
and amm/bloch.py: own element (27-node triquadratic Lagrange hex, Q2, 3x3x3 Gauss), own assembly, own periodic and
Bloch boundary handling (modulo node indexing with +-1 phases), own homogenization. Shared with amm: only the
geometry definition (amm.geometry voxelization of the design spec) and numerical libraries (numpy, scipy, pypardiso).

Scope: cells whose voxelization is EXACT (coverage 0 or 1 in every voxel: grid-aligned cube_bars). There a
conforming displacement model is a Rayleigh-Ritz model of the true continuum cell, so
  * effective stiffness (C in the Loewner order, hence C11, C44, bulk and E100 = 1/S11) is an UPPER bound of the
    exact value (minimum potential energy);
  * every eigenfrequency at a fixed Bloch k (band by band) is an UPPER bound of the exact one (min-max).
Tests against an amm certificate (rigorous up to solver round-off):
  static  amm guarded lower bound <= independent Q2 value     (else the certified lower bound is unsound)
  gap     independent band nb+1 at Gamma, X, M, R >= amm safe-interval upper edge (else the certified upper edge
          is unsound); band nb at these k <= safe lower edge is reported (consistency, not a bound test)
Bloch phases at Gamma, X, M, R are +-1, so the eigenproblems are real.

    indep_fe.py <out.json> [n ...]   (cells and certificates from verify_cells.json; see run_indep.py)
"""
from __future__ import annotations

import itertools

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

GP = (np.array([-np.sqrt(0.6), 0.0, np.sqrt(0.6)]), np.array([5 / 9, 8 / 9, 5 / 9]))
LOC = np.array(list(itertools.product(range(3), repeat=3)))[:, ::-1]  # (27, 3): node offsets (x fastest)


def _l(xi):
    return np.array([xi * (xi - 1) / 2, 1 - xi ** 2, xi * (xi + 1) / 2])


def _dl(xi):
    return np.array([xi - 0.5, -2 * xi, xi + 0.5])


def iso_D(nu: float) -> np.ndarray:
    """Isotropic stiffness, E = 1, Voigt order (xx, yy, zz, yz, zx, xy) with engineering shear strains."""
    lam, mu = nu / ((1 + nu) * (1 - 2 * nu)), 1 / (2 * (1 + nu))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[:3, :3] += 2 * mu * np.eye(3)
    D[3:, 3:] = mu * np.eye(3)
    return D


def element_matrices(h: float, nu: float):
    """Q2 element stiffness (81x81) and consistent mass (density 1) for a cube of edge h."""
    D = iso_D(nu)
    Ke, Me = np.zeros((81, 81)), np.zeros((81, 81))
    J = h / 2
    for (i, xi), (j, et), (k, ze) in itertools.product(list(enumerate(GP[0])), repeat=3):
        w = GP[1][i] * GP[1][j] * GP[1][k] * J ** 3
        lx, ly, lz = _l(xi), _l(et), _l(ze)
        dx, dy, dz = _dl(xi), _dl(et), _dl(ze)
        N = lx[LOC[:, 0]] * ly[LOC[:, 1]] * lz[LOC[:, 2]]
        G = np.stack([dx[LOC[:, 0]] * ly[LOC[:, 1]] * lz[LOC[:, 2]],
                      lx[LOC[:, 0]] * dy[LOC[:, 1]] * lz[LOC[:, 2]],
                      lx[LOC[:, 0]] * ly[LOC[:, 1]] * dz[LOC[:, 2]]]) / J  # (3, 27)
        B = np.zeros((6, 81))
        B[0, 0::3], B[1, 1::3], B[2, 2::3] = G[0], G[1], G[2]
        B[3, 1::3], B[3, 2::3] = G[2], G[1]
        B[4, 0::3], B[4, 2::3] = G[2], G[0]
        B[5, 0::3], B[5, 1::3] = G[1], G[0]
        Ke += w * B.T @ D @ B
        Nm = np.zeros((3, 81))
        for c in range(3):
            Nm[c, c::3] = N
        Me += w * Nm.T @ Nm
    return Ke, Me


class Q2Cell:
    """Solid voxels of an n^3 unit cell (cell edge 1) meshed with Q2 hexes on the periodic (2n)^3 node lattice."""

    def __init__(self, solid: np.ndarray, nu: float):
        n = solid.shape[0]
        self.n, self.nu = n, nu
        self.h = 1.0 / n
        self.Ke, self.Me = element_matrices(self.h, nu)
        ijk = np.argwhere(solid > 0.5)  # (ne, 3), axis order (x, y, z) = array axes (0, 1, 2)
        self.ne = len(ijk)
        self.density = self.ne / n ** 3
        g = 2 * ijk[:, None, :] + LOC[None, :, :]  # unwrapped node lattice coordinates (ne, 27, 3) in [0, 2n]
        self.wrap = g // (2 * n)  # 1 where the node wraps across the +x / +y / +z face
        gm = g % (2 * n)
        lin = (gm[..., 0] * (2 * n) + gm[..., 1]) * (2 * n) + gm[..., 2]
        used, inv = np.unique(lin, return_inverse=True)
        self.node = inv.reshape(self.ne, 27)
        self.nn = len(used)
        self.x = g * (self.h / 2)  # unwrapped coordinates (ne, 27, 3)

    def _dofs(self):
        return (3 * self.node[:, :, None] + np.arange(3)).reshape(self.ne, 81)

    def assemble(self, Ae, sign=None, chunk=4000):
        dofs = self._dofs()
        N = 3 * self.nn
        out = sp.csr_matrix((N, N))
        for s in range(0, self.ne, chunk):
            d = dofs[s:s + chunk]
            vals = np.broadcast_to(Ae, (len(d), 81, 81))
            if sign is not None:
                sg = sign[s:s + chunk]
                vals = vals * sg[:, :, None] * sg[:, None, :]
            rows = np.repeat(d[:, :, None], 81, axis=2)
            cols = np.repeat(d[:, None, :], 81, axis=1)
            out = out + sp.coo_matrix((vals.ravel(), (rows.ravel(), cols.ravel())), shape=(N, N)).tocsr()
        return out

    # ---- homogenization
    def homogenize(self) -> dict:
        from pypardiso import spsolve
        K = self.assemble(self.Ke)
        dofs = self._dofs()
        eps = np.eye(6)
        U0 = []  # affine displacement per load case, per element dof (ne, 81)
        F = np.zeros((3 * self.nn, 6))
        for c in range(6):
            e = eps[c]
            E = np.array([[e[0], e[5] / 2, e[4] / 2], [e[5] / 2, e[1], e[3] / 2], [e[4] / 2, e[3] / 2, e[2]]])
            u0 = (self.x @ E.T).reshape(self.ne, 81)
            U0.append(u0)
            fe = -u0 @ self.Ke.T
            np.add.at(F[:, c], dofs.ravel(), fe.ravel())
        keep = np.ones(3 * self.nn, bool)
        keep[:3] = False  # pin node 0 (rigid translation)
        Kr = K[keep][:, keep].tocsr()
        Ur = spsolve(Kr, F[keep])
        U = np.zeros_like(F)
        U[keep] = Ur
        C = np.zeros((6, 6))
        tot = [U0[c] + U[dofs, c] for c in range(6)]
        for a in range(6):
            KA = tot[a] @ self.Ke  # (ne, 81)
            for b in range(a, 6):
                C[a, b] = C[b, a] = float(np.sum(KA * tot[b]))
        res = float(np.abs(Kr @ Ur - F[keep]).max() / max(np.abs(F).max(), 1e-300))
        S = np.linalg.inv(C)
        return dict(C=C.tolist(), E100=float(1 / S[0, 0]), G=float(C[3, 3]), bulk=float((C[0, 0] + 2 * C[0, 1]) / 3),
                    nu100=float(-S[0, 1] / S[0, 0]), density=self.density, n=self.n, element="Q2", residual=res,
                    n_dofs=int(3 * self.nn))

    # ---- Bloch spectra at k with components 0 or pi (phases +-1: real problems)
    def spectrum(self, kpi: tuple, k_eig: int, sigma: float = -1e-3) -> np.ndarray:
        """Lowest normalized frequencies f* = f a / c_t at k = pi * kpi (kpi in {0,1}^3)."""
        from pypardiso import factorized
        sign = np.prod(np.where(self.wrap * np.array(kpi)[None, None, :] > 0, -1.0, 1.0), axis=2)  # (ne, 27)
        sign = np.repeat(sign, 3, axis=1)  # (ne, 81)
        K, M = self.assemble(self.Ke, sign), self.assemble(self.Me, sign)
        A = (K - sigma * M).tocsr()
        solve = factorized(A)
        op = spla.LinearOperator(A.shape, matvec=solve, dtype=float)
        vals, vecs = spla.eigsh(K, k=k_eig, M=M, sigma=sigma, which="LM", OPinv=op)
        o = np.argsort(vals)
        vals, vecs = vals[o], vecs[:, o]
        Kv, Mv = K @ vecs, M @ vecs
        res = np.linalg.norm(Kv - Mv * vals[None, :], axis=0) / np.maximum(np.linalg.norm(Kv, axis=0), 1e-300)
        self.last_eig_residual = float(res[vals > 1e-8].max()) if np.any(vals > 1e-8) else 0.0
        lam = np.clip(vals, 0, None)
        # rho = 1, E = 1: c_t = sqrt(G_s) = sqrt(1 / (2 (1 + nu))); f* = omega / (2 pi) * a / c_t
        return np.sqrt(lam) / (2 * np.pi) * np.sqrt(2 * (1 + self.nu))


HIGH_SYM = dict(G=(0, 0, 0), X=(1, 0, 0), M=(1, 1, 0), R=(1, 1, 1))


def self_test(nu=0.3):
    """Homogeneous solid: C equals D exactly; at X the lowest f* is 0.5 (shear wave, k = pi / a)."""
    c = Q2Cell(np.ones((3, 3, 3)), nu)
    h = c.homogenize()
    err = np.abs(np.array(h["C"]) - iso_D(nu)).max()
    f = c.spectrum((1, 0, 0), 6)
    return dict(C_error=float(err), X_lowest=float(f[0]), X_expected=0.5)
