"""V1b independent solver: triquadratic (Q2, 27-node) finite-cell model of a periodic cell with its own geometry
sampling, own assembly, own Floquet-Bloch constraint at ARBITRARY k, and own PARDISO calls (complex Hermitian).

Independence. Nothing from amm is imported. Shared with amm: the design definition (the published level-set /
distance formulas of the families, re-implemented here from their definitions with true periodic images), and the
numerical libraries (numpy, scipy, MKL PARDISO through ctypes). The Q2 element (shape functions, 3x3x3 Gauss) is
taken from scripts/verify/indep_fe.py (written separately from amm, element-checked against scikit-fem's
ElementHex2 to 1e-14; results/verification/skfem/summary.json).

Model.
* Mesh: the n^3 voxel grid of the unit cell, one Q2 hex per voxel, nodes on the periodic (2n)^3 lattice.
* Geometry: a voxel whose centre value is farther from the threshold than a Lipschitz bound times the half
  diagonal is uniformly solid or void. Every other voxel ("cut") is integrated by moment fitting (finite cell
  method): the 125 Legendre moments (degree <= 4 per direction) of the solid indicator are computed with s^3
  sub-cubes x 3^3 Gauss points per voxel (s = 5, 15 points per direction) and an anti-aliased indicator
  clip(1/2 - d/delta, 0, 1) (d: signed distance or phi/|grad phi|, delta = h/15), and the element matrices follow EXACTLY from the moments (the Q2 integrands are
  polynomials of degree <= 4 per direction). The void part carries a stiffness and mass floor alpha = 1e-6 so
  that K stays regular. Void voxels are dropped; the
  largest periodically face-connected component of non-void voxels is kept.
* Density-defined TPMS: the threshold is the density-quantile of the field on a 256^3 cell-centred grid.
* Homogenization: affine strain + periodic fluctuation, one node pinned, C = sum_e (u0+u)^T Ke (u0+u) (V = 1).
* Bloch: K(k), M(k) from the k = 0 matrices: every global entry (I, J) couples node I to node J through one element
  with a fixed lattice offset d_IJ = w_J - w_I (unique for n >= 3), so K(k)_IJ = K_IJ exp(i k.d_IJ). The
  Hermitian matrix K - sigma M is factored by PARDISO as complex Hermitian indefinite (mtype -4); the inertia
  (iparm 22/23) gives the number of eigenvalues below sigma (band index), and shift-invert Lanczos (scipy eigsh)
  around sigma gives the eigenvalues nearest to it. (amm uses hex8/hex8i elements, voxel sub-sample coverage, and
  the real 2N form with mtype -2; none of that is used here.)
Frequencies are normalized f* = f a / c_t with c_t = sqrt(E / (2 (1 + nu)) / rho), E = rho = 1.
"""
from __future__ import annotations

import ctypes
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import indep_fe  # noqa: E402  (Q2 element; independent of amm)

LOC = indep_fe.LOC  # (27, 3) node offsets 0..2, x fastest
ALPHA = 1e-6


# ============================================================ PARDISO (ctypes, complex or real)
_MKL = None


class Pardiso:
    """Minimal MKL PARDISO driver: mtype 2 (real SPD), -2 (real sym. indefinite), 4 (complex Hermitian PD),
    -4 (complex Hermitian indefinite). The matrix is passed as the UPPER triangle in CSR (1-based internally)."""

    def __init__(self, mtype: int):
        global _MKL
        if _MKL is None:
            from pypardiso.pardiso_wrapper import PyPardisoSolver
            _MKL = PyPardisoSolver().libmkl  # only to locate and load mkl_rt (once per process)
        self._f = _MKL.pardiso
        self._f.restype = None
        self.mtype = mtype
        self.pt = np.zeros(64, dtype=np.int64)
        self.iparm = np.zeros(64, dtype=np.int32)
        self.dtype = np.complex128 if mtype in (3, 4, -4, 6, 13) else np.float64
        self.A = None

    def _call(self, phase, b=None, nrhs=1):
        A = self.A
        n = A.shape[0]
        err = ctypes.c_int32(0)
        ia, ja = self._ia, self._ja
        if b is None:
            b = np.zeros((n, 1), dtype=self.dtype, order="F")
        x = np.zeros_like(b)
        i32 = ctypes.POINTER(ctypes.c_int32)
        self._f(self.pt.ctypes.data_as(ctypes.POINTER(ctypes.c_int64)), ctypes.byref(ctypes.c_int32(1)),
                ctypes.byref(ctypes.c_int32(1)), ctypes.byref(ctypes.c_int32(self.mtype)),
                ctypes.byref(ctypes.c_int32(phase)), ctypes.byref(ctypes.c_int32(n)),
                ctypes.c_void_p(self._data.ctypes.data), ia.ctypes.data_as(i32), ja.ctypes.data_as(i32),
                np.zeros(1, np.int32).ctypes.data_as(i32), ctypes.byref(ctypes.c_int32(nrhs)),
                self.iparm.ctypes.data_as(i32), ctypes.byref(ctypes.c_int32(0)),
                ctypes.c_void_p(b.ctypes.data), ctypes.c_void_p(x.ctypes.data), ctypes.byref(err))
        if err.value != 0:
            raise RuntimeError(f"PARDISO error {err.value} (phase {phase}, mtype {self.mtype})")
        return x

    def factor(self, U: sp.csr_matrix) -> dict:
        """U: upper triangle (CSR, sorted indices). Returns inertia and perturbed-pivot count."""
        if self.A is not None:
            self.free()
        U = U.tocsr()
        U.sort_indices()
        self.A = U
        self._data = np.ascontiguousarray(U.data.astype(self.dtype))
        self._ia = (U.indptr + 1).astype(np.int32)
        self._ja = (U.indices + 1).astype(np.int32)
        self.iparm[:] = 0
        if self.mtype in (-2, -4):  # explicit: METIS, no iterative refinement, perturbation 1e-8, Bunch-Kaufman
            self.iparm[0], self.iparm[1], self.iparm[7], self.iparm[9], self.iparm[20] = 1, 2, 0, 8, 1
        self._call(12)
        if self.mtype in (-2, -4) and self.iparm[13] > 0:  # perturbed pivots: refactor with scaling + weighted
            self._call(-1)                                   # matching and 2 refinement steps (robust, slower)
            self.pt[:] = 0
            self.iparm[:] = 0
            self.iparm[0], self.iparm[1], self.iparm[9] = 1, 3, 8
            self.iparm[10], self.iparm[12], self.iparm[7], self.iparm[20] = 1, 1, 2, 1
            self._call(12)
            self.robust = True
        return dict(n_pos=int(self.iparm[21]), n_neg=int(self.iparm[22]), n_perturbed=int(self.iparm[13]))

    def solve(self, b: np.ndarray) -> np.ndarray:
        b = np.asarray(b, dtype=self.dtype)
        one = b.ndim == 1
        B = np.asfortranarray(b.reshape(len(b), -1))
        x = self._call(33, B, nrhs=B.shape[1])
        return x[:, 0] if one else x

    def free(self):
        if self.A is not None:
            try:
                self._call(-1)
            except RuntimeError:
                pass
        self.A = None


# ============================================================ geometry (independent re-implementation)
def _bcc_segments():
    return [((0, 0, 0), (1, 1, 1)), ((1, 0, 0), (0, 1, 1)), ((0, 1, 0), (1, 0, 1)), ((0, 0, 1), (1, 1, 0))]


def _fcc_bonds():
    pts = [np.array(p, float) for p in itertools.product((0, 1), repeat=3)]
    for d in range(3):
        for s in (0.0, 1.0):
            p = np.full(3, 0.5)
            p[d] = s
            pts.append(p)
    out = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            if abs(np.linalg.norm(pts[i] - pts[j]) - 1 / np.sqrt(2)) < 1e-9:
                out.append((tuple(pts[i]), tuple(pts[j])))
    return out


def _sc_segments():
    return [((0, .5, .5), (1, .5, .5)), ((.5, 0, .5), (.5, 1, .5)), ((.5, .5, 0), (.5, .5, 1))]


def _periodic_set(segs, pad):
    """All periodic images (27 shifts) of the segments that come within `pad` of the unit cube, deduplicated."""
    out = {}
    for a, b in segs:
        for s in itertools.product((-1, 0, 1), repeat=3):
            A, B = np.array(a, float) + s, np.array(b, float) + s
            # distance from the segment's bounding box to the cube [0,1]^3
            lo, hi = np.minimum(A, B), np.maximum(A, B)
            gap = np.maximum(0, np.maximum(lo - 1, -hi))
            if np.linalg.norm(gap) <= pad:
                key = tuple(sorted([tuple(np.round(A, 9)), tuple(np.round(B, 9))]))
                out[key] = (A, B)
    return np.array([[a, b] for a, b in out.values()])


class Design:
    """phi(x) <= 0 is solid (x in cell coordinates, any real values; the design is 1-periodic)."""

    def __init__(self, spec: dict):
        self.spec = spec
        fam, kind, p = spec["family"], spec["kind"], spec["params"]
        self.fam, self.kind, self.p = fam, kind, p
        self.thr = 0.0
        if fam == "tpms":
            self.lip = self._tpms_lip()
            if p.get("density") is not None:
                g = (np.arange(256) + 0.5) / 256
                vals = []
                for i in range(256):  # slab-wise to bound memory
                    X = np.stack(np.meshgrid([g[i]], g, g, indexing="ij"), -1).reshape(-1, 3)
                    vals.append(self._tpms_raw(X).astype(np.float32))
                v = np.sort(np.concatenate(vals))
                self.thr = float(v[int(round(p["density"] * v.size)) - 1] + v[int(round(p["density"] * v.size))]) / 2
            else:
                self.thr = float(p["t"])
        elif fam == "struts":
            self.lip = 1.0
            segs = {"bcc": _bcc_segments, "octet": _fcc_bonds, "sc": _sc_segments}[kind]()
            self.r, self.R = float(p["r"]), float(p.get("R", 0.0) or 0.0)
            self.segs = _periodic_set(segs, max(self.r, self.R) + 0.05)
            nodes = np.unique(np.round(self.segs.reshape(-1, 3), 9), axis=0)
            if kind == "sc":  # the sc lattice node is the cell centre (bars through it)
                nodes = np.array([[0.5, 0.5, 0.5]])
            if kind == "bcc":
                nodes = np.array([[.5, .5, .5]] + [list(q) for q in itertools.product((0, 1), repeat=3)], float)
            self.nodes = _periodic_set([(tuple(q), tuple(q)) for q in nodes], self.R + 0.05)[:, 0, :]
        elif fam == "resonator":
            self.lip = 1.0
        else:
            raise ValueError(fam)

    # --- TPMS
    def _tpms_raw(self, x):
        X, Y, Z = (2 * np.pi * x[..., i] for i in range(3))
        k = self.kind
        if k == "schwarz_p":
            f = np.cos(X) + np.cos(Y) + np.cos(Z)
        elif k == "gyroid":
            f = np.sin(X) * np.cos(Y) + np.sin(Y) * np.cos(Z) + np.sin(Z) * np.cos(X)
        elif k == "diamond":
            f = (np.sin(X) * np.sin(Y) * np.sin(Z) + np.sin(X) * np.cos(Y) * np.cos(Z)
                 + np.cos(X) * np.sin(Y) * np.cos(Z) + np.cos(X) * np.cos(Y) * np.sin(Z))
        elif k == "iwp":
            f = (2 * (np.cos(X) * np.cos(Y) + np.cos(Y) * np.cos(Z) + np.cos(Z) * np.cos(X))
                 - (np.cos(2 * X) + np.cos(2 * Y) + np.cos(2 * Z)))
        else:
            raise ValueError(k)
        return np.abs(f) if self.p.get("mode", "network") == "sheet" else f

    def _tpms_lip(self):
        if self.kind == "schwarz_p":
            return 2 * np.pi * np.sqrt(3)
        g = (np.arange(96) + 0.5) / 96  # numerical bound with a 25 % margin for the other surfaces
        X = np.stack(np.meshgrid(g, g, g, indexing="ij"), -1)
        f = self._tpms_raw(X)
        gr = np.gradient(np.pad(f, 1, mode="wrap"), 1 / 96)
        return 1.25 * float(np.sqrt(sum(q ** 2 for q in gr)).max())

    def phi(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, float)
        if self.fam == "tpms":
            return self._tpms_raw(x) - self.thr
        x = np.mod(x, 1.0)
        sh = x.shape[:-1]
        P = x.reshape(-1, 3)
        if self.fam == "struts":
            d = np.full(len(P), np.inf)
            plo, phi_ = P.min(axis=0), P.max(axis=0)
            # exact pruning: ub = an upper bound of every point's nearest-axis distance (distance from the box centre
            # to a segment plus the box half diagonal); a segment whose bounding box lies farther than ub from the
            # point box cannot be any point's nearest segment
            cen, hdg = 0.5 * (plo + phi_), 0.5 * np.linalg.norm(phi_ - plo)
            dc = []
            for a, b in self.segs:
                ab = b - a
                t = np.clip(((cen - a) @ ab) / (ab @ ab), 0, 1)
                dc.append(np.linalg.norm(cen - a - t * ab))
            ub = min(dc) + hdg
            cap = ub
            for a, b in self.segs:
                slo, shi = np.minimum(a, b), np.maximum(a, b)
                if np.linalg.norm(np.maximum(0, np.maximum(slo - phi_, plo - shi))) > cap:
                    continue
                ab = b - a
                t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
                q = P - a - t[:, None] * ab
                d = np.minimum(d, np.einsum("ij,ij->i", q, q))
            ph = np.sqrt(d) - self.r
            if self.R > 0:
                dn = np.full(len(P), np.inf)
                ubn = min(np.linalg.norm(cen - c) for c in self.nodes) + hdg
                for c in self.nodes:
                    if np.linalg.norm(np.maximum(0, np.maximum(c - phi_, plo - c))) > ubn:
                        continue
                    dn = np.minimum(dn, np.einsum("ij,ij->i", P - c, P - c))
                ph = np.minimum(ph, np.sqrt(dn) - self.R)
            return ph.reshape(sh)
        c, w = self.p["c"], self.p["w"]
        X, Y, Z = (P[:, i] - 0.5 for i in range(3))
        if self.kind == "cube_bars":
            box = lambda hx, hy, hz: np.maximum(np.maximum(np.abs(X) - hx, np.abs(Y) - hy), np.abs(Z) - hz)
            core = box(c / 2, c / 2, c / 2)
            bars = np.minimum(np.minimum(box(1, w / 2, w / 2), box(w / 2, 1, w / 2)), box(w / 2, w / 2, 1))
        else:
            core = np.sqrt(X ** 2 + Y ** 2 + Z ** 2) - c
            bars = np.minimum(np.minimum(np.sqrt(Y ** 2 + Z ** 2), np.sqrt(X ** 2 + Z ** 2)), np.sqrt(X ** 2 + Y ** 2)) - w / 2
        return np.minimum(core, bars).reshape(sh)

    def sdist(self, x: np.ndarray) -> np.ndarray:
        """Signed distance estimate phi / |grad phi| (struts and resonators: phi is already a distance)."""
        ph = self.phi(x)
        if self.fam != "tpms":
            return ph
        x = np.asarray(x, float)
        if self.kind == "schwarz_p":
            gm = 2 * np.pi * np.sqrt(sum(np.sin(2 * np.pi * x[..., i]) ** 2 for i in range(3)))
        else:
            e = 1e-5
            gm = np.sqrt(sum(((self._tpms_raw(x + e * np.eye(3)[i]) - self._tpms_raw(x - e * np.eye(3)[i])) / (2 * e)) ** 2
                             for i in range(3)))
        return ph / np.maximum(gm, 1e-6)

    def density_fine(self, m: int = 256) -> float:
        """Solid fraction of the continuous design by midpoint sampling on an m^3 grid."""
        g = (np.arange(m) + 0.5) / m
        tot = 0
        for i in range(m):
            X = np.stack(np.meshgrid([g[i]], g, g, indexing="ij"), -1).reshape(-1, 3)
            tot += int((self.phi(X) <= 0).sum())
        return tot / m ** 3


# ============================================================ Q2 element tables
def _legendre01(x, deg=4):
    """Shifted Legendre polynomials P_0..P_deg on [0,1] at x (any shape) -> (..., deg+1)."""
    t = 2 * np.asarray(x, float) - 1
    P = [np.ones_like(t), t]
    for j in range(1, deg):
        P.append(((2 * j + 1) * t * P[j] - j * P[j - 1]) / (j + 1))
    return np.stack(P[:deg + 1], -1)


def _tensor_basis(X):
    """(m, 125) tensor shifted-Legendre basis (degree <= 4 per direction) at points X (m, 3) in [0,1]^3."""
    L = [_legendre01(X[:, d]) for d in range(3)]
    return np.einsum("mi,mj,mk->mijk", L[0], L[1], L[2]).reshape(len(X), 125)


def _BN(xi):
    """Q2 strain matrix B (6x81, per unit reference length h=2 -> scale later) and N (3x81) at xi in [-1,1]^3."""
    lx, ly, lz = (indep_fe._l(xi[i]) for i in range(3))
    dx, dy, dz = (indep_fe._dl(xi[i]) for i in range(3))
    N = lx[LOC[:, 0]] * ly[LOC[:, 1]] * lz[LOC[:, 2]]
    G = np.stack([dx[LOC[:, 0]] * ly[LOC[:, 1]] * lz[LOC[:, 2]],
                  lx[LOC[:, 0]] * dy[LOC[:, 1]] * lz[LOC[:, 2]],
                  lx[LOC[:, 0]] * ly[LOC[:, 1]] * dz[LOC[:, 2]]])
    B = np.zeros((6, 81))
    B[0, 0::3], B[1, 1::3], B[2, 2::3] = G[0], G[1], G[2]
    B[3, 1::3], B[3, 2::3] = G[2], G[1]
    B[4, 0::3], B[4, 2::3] = G[2], G[0]
    B[5, 0::3], B[5, 1::3] = G[1], G[0]
    Nm = np.zeros((3, 81))
    for c in range(3):
        Nm[c, c::3] = N
    return B, Nm


def moment_tables(h: float, nu: float):
    """Moment fitting. Every entry of the Q2 integrands B^T D B and N^T N is a polynomial of degree <= 4 per
    direction, so for ANY solid indicator chi on the element, Ke = sum_a Phi_K[a] m_a with the moments
    m_a = int chi(x) L_a(x) dx (L_a: tensor shifted-Legendre basis, 125 functions). Phi is obtained exactly from
    the integrands at the 5^3 Gauss points. Returns Phi_K, Phi_M (125, 6561), already scaled by the volume h^3."""
    D = indep_fe.iso_D(nu)
    g5, w5 = np.polynomial.legendre.leggauss(5)
    g5 = 0.5 * (g5 + 1)
    X = np.stack(np.meshgrid(g5, g5, g5, indexing="ij"), -1).reshape(-1, 3)
    FK = np.empty((len(X), 6561))
    FM = np.empty((len(X), 6561))
    for q, p in enumerate(X):
        B, Nm = _BN(2 * p - 1)
        B = B * (2.0 / h)
        FK[q] = (B.T @ D @ B).ravel() * h ** 3
        FM[q] = (Nm.T @ Nm).ravel() * h ** 3
    V = _tensor_basis(X)  # F(x_q) = sum_a c_a L_a(x_q): solve for the coefficients c
    cK, cM = np.linalg.solve(V, FK), np.linalg.solve(V, FM)
    # int chi F = sum_a c_a int chi L_a = sum_a c_a m_a  ->  Phi = c
    return cK, cM


# ============================================================ cell model
class Q2FCM:
    def __init__(self, design: Design, n: int, nu: float, s: int = 5, alpha: float = ALPHA, log=print, soft: bool = True):
        t0 = time.perf_counter()
        self.design, self.n, self.nu, self.h, self.s = design, n, nu, 1.0 / n, s
        h = self.h
        Ke_full, Me_full = indep_fe.element_matrices(h, nu)
        PhiK, PhiM = moment_tables(h, nu)
        # geometry sampling: s^3 sub-cubes x 3^3 Gauss points per cut element (exact moments wherever the indicator
        # is constant on a sub-cube), soft (anti-aliased) indicator with width delta = sub-cube edge / 3
        gq = 0.5 + 0.5 * np.array([-np.sqrt(0.6), 0.0, np.sqrt(0.6)])
        wg = np.array([5 / 18, 8 / 18, 5 / 18])
        g1 = ((np.arange(s)[:, None] + gq[None, :]) / s).ravel()
        w1 = (np.tile(wg, s) / s)
        P = np.stack(np.meshgrid(g1, g1, g1, indexing="ij"), -1).reshape(-1, 3)
        Wq = np.einsum("i,j,k->ijk", w1, w1, w1).ravel()
        Lq = _tensor_basis(P) * Wq[:, None]  # (q, 125): weights x basis
        delta = h / (3 * s)
        ijk = np.array(list(itertools.product(range(n), repeat=3)))  # (n^3, 3), axis 0 slowest
        ctr = (ijk + 0.5) * h
        ph_c = design.phi(ctr)
        half_diag = np.sqrt(3) * h / 2
        full = ph_c < -design.lip * half_diag
        void = ph_c > design.lip * half_diag
        cut = ~(full | void)
        cut_idx = np.flatnonzero(cut)
        blk = ijk[cut_idx] // 4  # spatially compact chunks (4^3-voxel blocks) for the geometry pruning
        cut_idx = cut_idx[np.lexsort((blk[:, 2], blk[:, 1], blk[:, 0]))]
        mom = np.zeros((len(cut_idx), 125))
        cmin = np.zeros(len(cut_idx))
        # sub-cube of every point, and the sub-cube centres; a sub-cube whose centre value clears the Lipschitz bound
        # (radius = sub-cube half diagonal + delta/2) has chi exactly 0 or 1 at all its 27 points (no evaluation)
        ia = np.arange(3 * s) // 3
        sub_of = ((ia[:, None, None] * s + ia[None, :, None]) * s + ia[None, None, :]).ravel()  # (q,)
        c1 = (np.arange(s) + 0.5) / s
        SC = np.stack(np.meshgrid(c1, c1, c1, indexing="ij"), -1).reshape(-1, 3)  # (s^3, 3)
        rad = design.lip * (np.sqrt(3) * h / (2 * s) + (delta / 2 if soft else 0.0))
        for c0 in range(0, len(cut_idx), 200):
            ids = cut_idx[c0:c0 + 200]
            pc = design.phi((ijk[ids][:, None, :] + SC[None, :, :]) * h)  # (m, s^3)
            sure = np.abs(pc) > rad
            ch = np.where((pc < 0)[:, sub_of], 1.0, 0.0)  # (m, q)
            need = ~sure[:, sub_of]
            if need.any():
                X = ((ijk[ids][:, None, :] + P[None, :, :]) * h)[need]
                ch[need] = (np.clip(0.5 - design.sdist(X) / delta, 0.0, 1.0) if soft
                            else (design.phi(X) <= 0).astype(float))
            mom[c0:c0 + 200] = ch @ Lq
            cmin[c0:c0 + 200] = ch.min(axis=1)
        frac = mom[:, 0]
        keep_cut = frac > 0
        allsolid = keep_cut & (cmin >= 1.0 - 1e-9)  # every sample point fully solid: a full element
        full[cut_idx[allsolid]] = True
        keep_cut &= ~allsolid
        # element list: full + cut with solid
        occ = np.zeros(n ** 3)
        occ[full] = 1.0
        occ[cut_idx[keep_cut]] = frac[keep_cut]
        grid = occ.reshape(n, n, n)
        lab, nl = self._periodic_label(grid > 0)
        vol = np.bincount(lab.ravel(), weights=grid.ravel())
        vol[0] = 0
        main = int(np.argmax(vol))
        removed = float(grid.sum() - vol[main])
        alive = (lab.ravel() == main)
        self.removed_fraction = removed / max(grid.sum(), 1e-300)
        self.n_components = int(nl)
        el = np.flatnonzero(alive)
        self.el_ijk = ijk[el]
        self.ne = len(el)
        is_cut = np.zeros(n ** 3, bool)
        is_cut[cut_idx[keep_cut]] = True
        pos_in_cut = -np.ones(n ** 3, int)
        pos_in_cut[cut_idx] = np.arange(len(cut_idx))
        self.cut_local = np.flatnonzero(is_cut[el])  # indices into the element list
        mom_el = mom[pos_in_cut[el[self.cut_local]]]
        e0 = np.zeros(125)
        e0[0] = 1.0  # moments of the constant indicator 1
        wq = mom_el + alpha * (e0[None, :] - mom_el)  # chi + alpha (1 - chi)
        self.Ke_cut = (wq @ PhiK).reshape(-1, 81, 81)
        self.Me_cut = (wq @ PhiM).reshape(-1, 81, 81)
        self.Ke_cut = 0.5 * (self.Ke_cut + self.Ke_cut.transpose(0, 2, 1))
        self.Me_cut = 0.5 * (self.Me_cut + self.Me_cut.transpose(0, 2, 1))
        self.full_check = float(np.abs((e0 @ PhiK).reshape(81, 81) - Ke_full).max() / np.abs(Ke_full).max())
        self.Ke_full, self.Me_full = Ke_full, Me_full
        self.solid_volume = float((np.count_nonzero(alive & full) + mom_el[:, 0].sum()) * h ** 3)
        self.density = self.solid_volume
        self.n_cut, self.n_full = len(self.cut_local), self.ne - len(self.cut_local)
        # nodes on the periodic (2n)^3 lattice
        g = 2 * self.el_ijk[:, None, :] + LOC[None, :, :]
        self.wrap = (g // (2 * n)).astype(np.int8)  # (ne, 27, 3)
        gm = g % (2 * n)
        lin = (gm[..., 0] * (2 * n) + gm[..., 1]) * (2 * n) + gm[..., 2]
        used, inv = np.unique(lin, return_inverse=True)
        self.node = inv.reshape(self.ne, 27)
        self.nn = len(used)
        self.ndof = 3 * self.nn
        self.x = g * (h / 2)  # unwrapped node coordinates (ne, 27, 3)
        self.dofs = (3 * self.node[:, :, None] + np.arange(3)).reshape(self.ne, 81)
        self._pattern()
        self.setup_s = round(time.perf_counter() - t0, 1)
        log(f"  Q2FCM n={n} s={s}: ne={self.ne} (cut {self.n_cut}), ndof={self.ndof}, density={self.density:.5f}, "
            f"removed={self.removed_fraction:.2e}, setup {self.setup_s}s")

    @staticmethod
    def _periodic_label(mask):
        lab, nl = ndimage.label(mask)
        parent = np.arange(nl + 1)

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for d in range(3):
            a, b = np.take(lab, 0, axis=d), np.take(lab, -1, axis=d)
            both = (a > 0) & (b > 0)
            for u, v in set(zip(a[both].tolist(), b[both].tolist())):
                ru, rv = find(u), find(v)
                if ru != rv:
                    parent[max(ru, rv)] = min(ru, rv)
        roots = np.array([find(i) for i in range(nl + 1)])
        _, inv = np.unique(roots, return_inverse=True)
        return inv[lab], int(inv.max())

    def _elem_vals(self, which):
        """(ne, 81, 81) element matrices as a lazy chunk generator: yields (index array, values)."""
        full_mat = self.Ke_full if which == "K" else self.Me_full
        cut_mats = self.Ke_cut if which == "K" else self.Me_cut
        is_cut = np.zeros(self.ne, bool)
        is_cut[self.cut_local] = True
        full_ids = np.flatnonzero(~is_cut)
        for c in range(0, len(full_ids), 3000):
            ids = full_ids[c:c + 3000]
            yield ids, np.broadcast_to(full_mat, (len(ids), 81, 81))
        for c in range(0, len(self.cut_local), 3000):
            yield self.cut_local[c:c + 3000], cut_mats[c:c + 3000]

    def _pattern(self):
        """Global CSR pattern, the scatter map of every element entry, and the lattice offset d_IJ per entry."""
        rows = np.repeat(self.dofs[:, :, None], 81, axis=2).reshape(-1)
        cols = np.repeat(self.dofs[:, None, :], 81, axis=1).reshape(-1)
        lin = rows.astype(np.int64) * self.ndof + cols
        del rows, cols
        uniq, scatter = np.unique(lin, return_inverse=True)
        del lin
        self.scatter = scatter.reshape(self.ne, 81 * 81).astype(np.int64)
        r = (uniq // self.ndof).astype(np.int64)
        c = (uniq % self.ndof).astype(np.int64)
        self.indptr = np.zeros(self.ndof + 1, np.int64)
        np.add.at(self.indptr, r + 1, 1)
        self.indptr = np.cumsum(self.indptr)
        self.indices = c.astype(np.int32)
        self.nnz = len(uniq)
        self.rows = r.astype(np.int32)
        self.upper = self.indices >= self.rows

    def _lattice_offsets(self):
        """Lattice offset per global entry: w(col node) - w(row node) for an element containing the pair, checked to
        be the same for every element that contributes to the entry (unique for n >= 3)."""
        if hasattr(self, "dlat"):
            return self.dlat
        w81 = np.repeat(self.wrap, 3, axis=1).astype(np.int8)  # (ne, 81, 3)
        dW = (w81[:, None, :, :] - w81[:, :, None, :]).reshape(-1, 3)
        sc = self.scatter.ravel()
        self.dlat = np.zeros((self.nnz, 3), np.int8)
        self.dlat[sc] = dW
        cnt = np.bincount(sc, minlength=self.nnz)
        for d in range(3):
            tot = np.bincount(sc, weights=dW[:, d].astype(float), minlength=self.nnz)
            assert np.array_equal(tot, cnt * self.dlat[:, d]), "lattice offset not unique per entry (n too small?)"
        return self.dlat

    def _assemble_data(self, which):
        data = np.zeros(self.nnz)
        for ids, vals in self._elem_vals(which):
            data += np.bincount(self.scatter[ids].ravel(), weights=np.asarray(vals).reshape(-1), minlength=self.nnz)
        return data

    def matrices(self):
        if not hasattr(self, "_K0"):
            self._K0 = self._assemble_data("K")
            self._M0 = self._assemble_data("M")
        return self._K0, self._M0

    def csr(self, data):
        return sp.csr_matrix((data, self.indices, self.indptr), shape=(self.ndof, self.ndof))

    # ---------------- homogenization
    def homogenize(self) -> dict:
        t0 = time.perf_counter()
        K0, _ = self.matrices()
        K = self.csr(K0)
        eps = np.eye(6)
        F = np.zeros((self.ndof, 6))
        U0 = []
        for cidx in range(6):
            e = eps[cidx]
            E = np.array([[e[0], e[5] / 2, e[4] / 2], [e[5] / 2, e[1], e[3] / 2], [e[4] / 2, e[3] / 2, e[2]]])
            U0.append((self.x @ E.T).reshape(self.ne, 81))
        for ids, vals in self._elem_vals("K"):
            vals = np.asarray(vals)
            for cidx in range(6):
                fe = -np.einsum("eij,ej->ei", vals, U0[cidx][ids])
                F[:, cidx] += np.bincount(self.dofs[ids].ravel(), weights=fe.ravel(), minlength=self.ndof)
        keep = np.ones(self.ndof, bool)
        keep[:3] = False
        Kr = K[keep][:, keep].tocsr()
        ps = Pardiso(2)
        st = ps.factor(sp.triu(Kr, format="csr"))
        Ur = ps.solve(F[keep])
        ps.free()
        res = float(np.abs(Kr @ Ur - F[keep]).max() / max(np.abs(F).max(), 1e-300))
        U = np.zeros_like(F)
        U[keep] = Ur
        C = np.zeros((6, 6))
        for ids, vals in self._elem_vals("K"):
            vals = np.asarray(vals)
            tot = [U0[c][ids] + U[self.dofs[ids], c] for c in range(6)]
            for a in range(6):
                KA = np.einsum("eij,ej->ei", vals, tot[a])
                for b in range(a, 6):
                    C[a, b] += float(np.sum(KA * tot[b]))
        C = np.triu(C) + np.triu(C, 1).T
        S = np.linalg.inv(C)
        C11 = float(np.mean(np.diag(C)[:3]))
        C12 = float(np.mean([C[0, 1], C[0, 2], C[1, 2]]))
        C44 = float(np.mean(np.diag(C)[3:]))
        E100 = float(np.mean(1 / np.diag(S)[:3]))
        nu100 = float(np.mean([-S[0, 1] / S[0, 0], -S[0, 2] / S[0, 0], -S[1, 2] / S[1, 1]]))
        return dict(C=C.tolist(), C11=C11, C12=C12, C44=C44, G=C44, E100=E100, bulk=(C11 + 2 * C12) / 3,
                    nu100=nu100, density=self.density, n=self.n, s=self.s, residual=res, n_dofs=self.ndof,
                    n_perturbed=st["n_perturbed"], min_eig=float(np.linalg.eigvalsh(C)[0]),
                    seconds=round(time.perf_counter() - t0, 1), setup_s=self.setup_s,
                    removed_fraction=self.removed_fraction, n_cut=self.n_cut, n_full=self.n_full)

    # ---------------- Bloch
    def _real2n_upper(self, a: np.ndarray) -> sp.csr_matrix:
        """Upper triangle of [[Re A, -Im A], [Im A, Re A]] (real symmetric, 2N) from the complex data of A on the
        global pattern; each eigenvalue of A appears twice. The pattern is built once."""
        N = self.ndof
        if not hasattr(self, "_r2n"):
            up = self.upper
            e = np.arange(self.nnz)
            R = np.concatenate([self.rows[up], self.rows, N + self.rows[up]]).astype(np.int64)
            C = np.concatenate([self.indices[up], N + self.indices, N + self.indices[up]]).astype(np.int64)
            src = np.concatenate([e[up], e, e[up]])
            part = np.concatenate([np.zeros(up.sum(), np.int8), np.ones(self.nnz, np.int8), np.zeros(up.sum(), np.int8)])
            o = np.lexsort((C, R))
            R, C, src, part = R[o], C[o], src[o], part[o]
            ip = np.zeros(2 * N + 1, np.int64)
            np.add.at(ip, R + 1, 1)
            self._r2n = (np.cumsum(ip), C.astype(np.int32), src, part.astype(bool))
        ip, C, src, part = self._r2n
        v = np.where(part, -a.imag[src], a.real[src])
        return sp.csr_matrix((v, C, ip), shape=(2 * N, 2 * N))

    def sigma(self, f):
        return float((2 * np.pi * f / np.sqrt(2 * (1 + self.nu))) ** 2)

    def to_f(self, lam):
        return np.sqrt(np.clip(np.real(lam), 0, None)) / (2 * np.pi) * np.sqrt(2 * (1 + self.nu))

    def near(self, k, f_center: float, nev: int = 8, tol: float = 1e-9, sigma: float | None = None) -> dict:
        """Eigenvalues nearest to f_center at wave vector k (radians per cell edge), and the number of eigenvalues
        below f_center (PARDISO inertia of K(k) - sigma M(k))."""
        from scipy.sparse.linalg import LinearOperator, eigsh
        K0, M0 = self.matrices()
        ph = np.exp(1j * (self._lattice_offsets().astype(float) @ np.asarray(k, float)))
        Kd, Md = K0 * ph, M0 * ph
        s = self.sigma(f_center) if sigma is None else sigma
        ps = Pardiso(-2)
        st = ps.factor(self._real2n_upper(Kd - s * Md))
        st = dict(st, n_neg=st["n_neg"] // 2, odd=st["n_neg"] % 2)
        N = self.ndof

        def _inv(v):
            v = np.asarray(v).ravel()
            y = ps.solve(np.concatenate([v.real, v.imag]))
            return y[:N] + 1j * y[N:]
        K, M = self.csr(Kd), self.csr(Md)
        op = LinearOperator(K.shape, matvec=_inv, dtype=complex)
        rng = np.random.default_rng(7)
        v0 = rng.standard_normal(self.ndof) + 1j * rng.standard_normal(self.ndof)
        while True:  # widen until eigenvalues on both sides of the shift are found (or nev = 32)
            w, V = eigsh(K, k=nev, M=M, sigma=s, OPinv=op, which="LM", tol=tol, v0=v0)
            fw = self.to_f(np.real(w))
            if sigma is not None or ((fw < f_center).any() and (fw >= f_center).any()) or nev >= 32:
                break
            nev = min(2 * nev, 32)
        ps.free()
        o = np.argsort(np.real(w))
        w, V = np.real(w[o]), V[:, o]
        R = K @ V - (M @ V) * w[None, :]
        res = np.linalg.norm(R, axis=0) / np.maximum(np.linalg.norm(K @ V, axis=0), 1e-300)
        f = self.to_f(w)
        res = res[f > 1e-3] if np.any(f > 1e-3) else res[:0]  # rigid translations at Gamma (f = 0) excluded
        res = res if len(res) else np.zeros(1)
        nb = st["n_neg"]
        below = f[f < f_center]
        above = f[f >= f_center]
        return dict(k=list(map(float, k)), f=f.tolist(), n_below=nb, n_perturbed=st["n_perturbed"], odd=st["odd"],
                    top_below=float(below.max()) if len(below) else None,
                    bottom_above=float(above.min()) if len(above) else None,
                    n_found_below=int(len(below)), eig_res=float(res.max()), ndof=self.ndof)

    def lowest(self, k, nev: int = 15) -> dict:
        """Lowest nev frequencies at k (shift just below zero)."""
        return self.near(k, 0.0, nev=nev, sigma=-self.sigma(0.01))


def self_test(log=print):
    """(1) homogeneous solid: C = D; X-point lowest f* = 0.5. (2) exact grid-aligned cube_bars: Q2FCM reproduces
    indep_fe.Q2Cell (same space, exact geometry) to round-off."""
    out = {}
    d = Design({"family": "resonator", "kind": "cube_bars", "params": {"c": 1.2, "w": 1.2}})  # whole cell solid
    m = Q2FCM(d, 4, 0.3, s=2, log=log)
    h = m.homogenize()
    out["homog_C_err"] = float(np.abs(np.array(h["C"]) - indep_fe.iso_D(0.3)).max())
    r = m.near((np.pi, 0, 0), 0.45, nev=6)
    out["X_bottom_above_0.45"] = r["bottom_above"]
    kk = np.array([np.pi * 0.3, np.pi * 0.2, 0.1])
    r2 = m.near(kk, 0.2, nev=6)  # homogeneous: lowest two (shear) f* = |k| / (2 pi), then longitudinal
    out["general_k_shear"] = [r2["top_below"], float(np.linalg.norm(kk) / (2 * np.pi)), r2["n_below"]]
    spec = {"family": "resonator", "kind": "cube_bars", "params": {"c": 0.5, "w": 0.2}}
    d2 = Design(spec)
    m2 = Q2FCM(d2, 20, 0.3, s=2, log=log, soft=False)  # sharp indicator; faces at 0.25 / 0.4 / 0.6 / 0.75: grid aligned at n = 20
    q = indep_fe.Q2Cell((d2.phi(((np.array(list(itertools.product(range(20), repeat=3))) + 0.5) / 20)) <= 0)
                        .reshape(20, 20, 20).astype(float), 0.3)
    hq, h2 = q.homogenize(), m2.homogenize()
    out["exact_cell_C_rel_diff"] = float(np.abs(np.array(hq["C"]) - np.array(h2["C"])).max() / np.abs(hq["C"]).max())
    fx = indep_fe.Q2Cell.spectrum(q, (1, 1, 0), 10)
    r3 = m2.near((np.pi, np.pi, 0), float(fx[6] * 0.5 + fx[5] * 0.5), nev=4)
    out["exact_cell_M_band7"] = [float(fx[6]), r3["bottom_above"], r3["n_below"]]
    return out


if __name__ == "__main__":
    print(self_test())
