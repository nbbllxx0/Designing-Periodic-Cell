"""Voxel hex8 finite elements on a periodic unit cell, with finite-cell integration of partial voxels.

A `CellMesh` is built once per voxelized design. It holds the element-to-DOF map on the periodic node set (void
elements removed, unused nodes dropped), the faces each element node wrapped across, a precomputed CSR pattern
with a scatter map, and per-element stiffness and mass matrices.

Partial voxels (finite cell method, Parvizian, Duester and Rank 2007): an element that is only partly solid
integrates B^T D B and N^T rho N over its own solid sub-samples (the same s^3 sub-samples used for its
coverage), so the material sits where it really is inside the element. Scaling a whole voxel by its coverage
("Voigt voxel") instead smears the material to the voxel edge and inflates bending stiffness: on the cube-and-
bars cell it shifted gap edges by ~15% between grid-aligned and non-aligned resolutions.

Assembling K or M for any Bloch wave vector is one vectorized fill of the CSR data array.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp

# local node order: node a has offsets ((a>>0)&1, (a>>1)&1, (a>>2)&1)
OFF = np.array([[(a >> 0) & 1, (a >> 1) & 1, (a >> 2) & 1] for a in range(8)])
SGN = 2 * OFF - 1
ELEMENT = "hex8i"  # full voxels: "hex8" (trilinear) or "hex8i" (Wilson-Taylor incompatible modes)


def elastic_D(E: float = 1.0, nu: float = 0.3) -> np.ndarray:
    lam = E * nu / ((1 + nu) * (1 - 2 * nu))
    mu = E / (2 * (1 + nu))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[np.arange(3), np.arange(3)] += 2 * mu
    D[3:, 3:] = np.eye(3) * mu  # engineering shear strains (yz, xz, xy)
    return D


def _strain_B(dN: np.ndarray) -> np.ndarray:
    """B (6 x 3m) from shape-function gradients dN (3 x m)."""
    m = dN.shape[1]
    B = np.zeros((6, 3 * m))
    for a in range(m):
        bx, by, bz = dN[:, a]
        B[0, 3 * a] = bx
        B[1, 3 * a + 1] = by
        B[2, 3 * a + 2] = bz
        B[3, 3 * a + 1] = bz
        B[3, 3 * a + 2] = by
        B[4, 3 * a] = bz
        B[4, 3 * a + 2] = bx
        B[5, 3 * a] = by
        B[5, 3 * a + 1] = bx
    return B


def shape_N(p: np.ndarray) -> np.ndarray:
    return np.prod((1 + SGN * p) / 2, axis=1)  # (8,)


def B_at(p: np.ndarray, h: float) -> np.ndarray:
    """Trilinear B (6x24) at local point p in [-1,1]^3 of a cube of edge h."""
    f = (1 + SGN * p) / 2
    dN = np.empty((3, 8))
    for d in range(3):
        o = [j for j in range(3) if j != d]
        dN[d] = SGN[:, d] / 2 * f[:, o[0]] * f[:, o[1]] * (2.0 / h)
    return _strain_B(dN)


def bubble_B(p: np.ndarray, h: float) -> np.ndarray:
    """B (6x9) of the incompatible modes (1 - xi^2), (1 - eta^2), (1 - zeta^2) in each direction."""
    dN = np.zeros((3, 3))
    for m in range(3):
        dN[m, m] = -2 * p[m] * 2.0 / h
    return _strain_B(dN)


GAUSS2 = [np.array(p) for p in itertools.product(*[np.array([-1.0, 1.0]) / np.sqrt(3.0)] * 3)]


def hex8_ke(h: float, D: np.ndarray, element: str | None = None) -> np.ndarray:
    """Stiffness of a full cube of edge h. "hex8i" statically condenses 9 incompatible bubble modes (less
    locking in bending); it passes the patch test on cubes, so affine homogenization loads stay exact."""
    element = element or ELEMENT
    w = (h / 2) ** 3
    kuu = np.zeros((24, 24))
    kua = np.zeros((24, 9))
    kaa = np.zeros((9, 9))
    for p in GAUSS2:
        B = B_at(p, h)
        kuu += B.T @ D @ B * w
        if element == "hex8i":
            Ba = bubble_B(p, h)
            kua += B.T @ D @ Ba * w
            kaa += Ba.T @ D @ Ba * w
    if element == "hex8i":
        kuu = kuu - kua @ np.linalg.solve(kaa, kua.T)
    elif element != "hex8":
        raise ValueError(element)
    return 0.5 * (kuu + kuu.T)


def hex8_me(h: float, rho: float = 1.0) -> np.ndarray:
    dist = np.abs(OFF[:, None, :] - OFF[None, :, :]).sum(-1)
    m = rho * h**3 / 216.0 * 2.0 ** (3 - dist)
    return np.kron(m, np.eye(3))


_FCM_CACHE: dict = {}


def fcm_tables(h: float, D: np.ndarray, s: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-sub-sample contributions (s^3 x 576) to K and M; sub-sample q = (a, b, c) in C order, local coords
    xi = -1 + (2a+1)/s etc. Midpoint rule on each sub-cube (error O(1/s^2) for these quadratic integrands)."""
    key = (h, s, D.tobytes())
    if key not in _FCM_CACHE:
        c = -1 + (2 * np.arange(s) + 1) / s
        w = (h / s) ** 3
        GK, GM = [], []
        for p in itertools.product(c, c, c):
            p = np.array(p)
            B = B_at(p, h)
            N = shape_N(p)
            GK.append((B.T @ D @ B * w).ravel())
            GM.append((np.kron(np.outer(N, N), np.eye(3)) * w).ravel())
        _FCM_CACHE[key] = (np.array(GK), np.array(GM))
    return _FCM_CACHE[key]


@dataclass
class CellMesh:
    n: int
    nu: float
    mask: np.ndarray  # (n,n,n) bool, voxels carrying material
    weights: np.ndarray  # (ne,) solid coverage of each element in (0,1]
    ne: int
    nnode: int
    ndof: int
    el_ijk: np.ndarray  # (ne,3)
    wrap: np.ndarray  # (ne,8,3) int8: node crossed the +face in direction d
    edof: np.ndarray  # (ne,24) global DOF indices
    Ke: np.ndarray = field(repr=False, default=None)  # (ne,24,24)
    Me: np.ndarray = field(repr=False, default=None)  # (ne,24,24)
    indptr: np.ndarray = field(repr=False, default=None)
    indices: np.ndarray = field(repr=False, default=None)
    scatter: np.ndarray = field(repr=False, default=None)  # (ne*576,) position in CSR data
    _r2n: dict = field(repr=False, default_factory=dict)

    @property
    def h(self) -> float:
        return 1.0 / self.n

    @property
    def density(self) -> float:
        return float(self.weights.sum() / self.n**3)

    def _phases(self, k):
        if k is None or not np.any(k):
            return None
        ph = np.exp(1j * (self.wrap @ np.asarray(k, float)))  # (ne,8)
        return np.repeat(ph, 3, axis=1)  # (ne,24)

    def element_values(self, which: str = "K", k=None) -> np.ndarray:
        E = self.Ke if which == "K" else self.Me
        ph = self._phases(k)
        if ph is None:
            return E.ravel()
        return (np.conj(ph)[:, :, None] * E * ph[:, None, :]).ravel()

    def csr_data(self, vals: np.ndarray) -> np.ndarray:
        nnz = len(self.indices)
        if np.iscomplexobj(vals):
            re = np.bincount(self.scatter, weights=vals.real, minlength=nnz)
            im = np.bincount(self.scatter, weights=vals.imag, minlength=nnz)
            return re + 1j * im
        return np.bincount(self.scatter, weights=vals, minlength=nnz)

    def assemble(self, which: str = "K", k=None) -> sp.csr_matrix:
        data = self.csr_data(self.element_values(which, k))
        return sp.csr_matrix((data, self.indices, self.indptr), shape=(self.ndof, self.ndof))

    # --------- real 2N upper-triangle form for PARDISO (mtype -2) ---------
    def real2n_upper_pattern(self):
        """CSR pattern of triu([[Re,-Im],[Im,Re]]) and the map from it to the complex CSR data."""
        if "pat" in self._r2n:
            return self._r2n["pat"]
        N = self.ndof
        rows = np.repeat(np.arange(N), np.diff(self.indptr))
        cols = self.indices
        e = np.arange(len(cols))
        up = cols >= rows
        R = np.concatenate([rows[up], rows, N + rows[up]])
        C = np.concatenate([cols[up], N + cols, N + cols[up]])
        src = np.concatenate([e[up], e, e[up]])
        part = np.concatenate([np.zeros(up.sum(), np.int8), np.ones(len(e), np.int8), np.zeros(up.sum(), np.int8)])
        order = np.lexsort((C, R))
        R, C, src, part = R[order], C[order], src[order], part[order]
        indptr = np.zeros(2 * N + 1, np.int64)
        np.add.at(indptr, R + 1, 1)
        indptr = np.cumsum(indptr)
        pat = (indptr.astype(np.int32), C.astype(np.int32), src, part)
        self._r2n["pat"] = pat
        return pat

    def real2n_upper(self, cdata: np.ndarray) -> sp.csr_matrix:
        indptr, indices, src, part = self.real2n_upper_pattern()
        v = np.where(part == 0, cdata.real[src], -cdata.imag[src])
        return sp.csr_matrix((v, indices, indptr), shape=(2 * self.ndof, 2 * self.ndof))


def build_mesh(field: np.ndarray, sub: np.ndarray | None = None, nu: float = 0.3,
               element: str | None = None, fcm_alpha: float = 0.0) -> CellMesh:
    """field: bool mask or float coverage (n,n,n). sub: optional sub-sample solid fractions (n,s,n,s,n,s) for
    finite-cell integration of partial voxels; without it partial voxels are coverage-scaled (Voigt voxels).
    fcm_alpha: stiffness floor added to partial voxels (alpha * full-voxel Ke), the usual finite-cell remedy for a
    partial voxel with one or two solid sub-samples (rank-6 midpoint stiffness) whose corner nodes no other element
    touches; those nodes then carry zero-energy modes and K is singular. Default 0: used only as a retry."""
    field = np.asarray(field)
    mask = field > 0
    n = mask.shape[0]
    assert mask.shape == (n, n, n), "cubic voxel grids only"
    el = np.argwhere(mask)
    if len(el) == 0:
        raise ValueError("empty geometry")
    weights = field[mask].astype(float) if field.dtype != bool else np.ones(len(el))
    h = 1.0 / n
    D = elastic_D(1.0, nu)
    ke, me = hex8_ke(h, D, element), hex8_me(h)
    Ke = np.broadcast_to(ke, (len(el), 24, 24)).copy()
    Me = np.broadcast_to(me, (len(el), 24, 24)).copy()
    part = np.flatnonzero(weights < 1.0 - 1e-12)
    if len(part):
        if sub is not None:
            s = sub.shape[1]
            GK, GM = fcm_tables(h, D, s)
            i, j, k = el[part].T
            chi = sub[i, :, j, :, k, :].reshape(len(part), s**3)  # advanced indices first, then (a, b, c)
            Ke[part] = (chi @ GK).reshape(-1, 24, 24)
            Me[part] = (chi @ GM).reshape(-1, 24, 24)
        else:
            Ke[part] *= weights[part, None, None]
            Me[part] *= weights[part, None, None]
        if fcm_alpha:
            Ke[part] += fcm_alpha * ke
    nodes = el[:, None, :] + OFF[None, :, :]
    wrap = (nodes // n).astype(np.int8)
    pn = nodes % n
    pid = pn[..., 0] + n * (pn[..., 1] + n * pn[..., 2])
    used, inv = np.unique(pid, return_inverse=True)
    inv = inv.reshape(pid.shape)
    edof = (3 * inv[..., None] + np.arange(3)).reshape(len(el), 24)
    ndof = 3 * len(used)
    rows = np.repeat(edof, 24, axis=1).ravel().astype(np.int64)
    cols = np.tile(edof, (1, 24)).ravel().astype(np.int64)
    uniq, scatter = np.unique(rows * ndof + cols, return_inverse=True)
    r = uniq // ndof
    indptr = np.zeros(ndof + 1, np.int64)
    np.add.at(indptr, r + 1, 1)
    indptr = np.cumsum(indptr)
    return CellMesh(n=n, nu=nu, mask=mask, weights=weights, ne=len(el), nnode=len(used), ndof=ndof, el_ijk=el,
                    wrap=wrap, edof=edof, Ke=Ke, Me=Me, indptr=indptr.astype(np.int32),
                    indices=(uniq % ndof).astype(np.int32), scatter=scatter.astype(np.int64))
