"""Finite (non-periodic or partly periodic) voxel FE for V6, reusing amm's voxelization and element matrices.

What amm lacks for V6 and this module adds (standalone, nothing in amm/ is changed):
  * a mesh of a TILED cell (Nx x Ny x Nz copies of one voxelized cell) with periodicity chosen per direction:
    the 6-cell chain is periodic in x and y (Bloch k_perp = 0) and open in z; the finite block is open in x, y, z;
  * Dirichlet conditions on the end faces (rigid, bonded plates), reaction forces;
  * a frequency-domain solve with hysteretic damping, K* = (1 + i eta) K, on the real symmetric 2N form;
  * the homogenized macro block: the same mesh builder on a uniform grid with an anisotropic D = C*.

Reused from amm: geometry.design_cell (anti-aliased coverage + sub-samples, cleaned to the largest periodic
component; the certificate's geometry model), fem.hex8_ke / hex8_me / fcm_tables / elastic_D (hex8i full voxels,
finite-cell integration of partial voxels, exactly as fem.build_mesh), pardiso.Pardiso (MKL PARDISO).

Units: normalized as in amm (E_s = 1, rho_s = 1, cell edge a = 1). Frequencies f* = f a / c_t; omega^2 =
bloch.f_to_sigma(f*, nu). Static stiffness k* = F / delta in units of E_s a (physical k = k* E_s a).
"""
from __future__ import annotations

import time

import numpy as np
import scipy.sparse as sp

import amm  # noqa: F401  (MKL before torch)
from amm import bloch, fem, geometry
from amm.fem import OFF
from amm.pardiso import Pardiso


class TiledMesh:
    """Voxel mesh of an Nx x Ny x Nz tiling of one cell (n^3 voxels per cell), or of a uniform block (cov=None).

    cov (n,n,n) coverage and sub6 (n,s,n,s,n,s) sub-samples of ONE cell, from geometry.design_cell (or an STL
    re-voxelization). periodic: (px, py, pz) booleans; a periodic direction identifies its first and last node plane.
    D: 6x6 material matrix (Voigt 11 22 33 23 13 12, engineering shear); default isotropic elastic_D(1, nu).
    """

    def __init__(self, cov, sub6, tiles=(1, 1, 6), periodic=(True, True, False), nu=0.3, D=None, element="hex8i",
                 with_mass=True):
        t0 = time.perf_counter()
        cov = np.asarray(cov, float)
        n = cov.shape[0]
        self.n, self.tiles, self.periodic, self.nu = n, tuple(tiles), tuple(periodic), nu
        h = 1.0 / n
        D = fem.elastic_D(1.0, nu) if D is None else np.asarray(D, float)
        ke, me = fem.hex8_ke(h, D, element), fem.hex8_me(h)
        el = np.argwhere(cov > 0)                       # local solid voxels of one cell
        w = cov[cov > 0]
        part = np.flatnonzero(w < 1.0 - 1e-12)
        # per-local-element matrices: index 0 = full voxel, 1.. = partial voxels (finite-cell, as fem.build_mesh)
        kind = np.zeros(len(el), np.int64)
        Kloc, Mloc = [ke], [me]
        if len(part):
            if sub6 is None:
                Kp = w[part, None, None] * ke
                Mp = w[part, None, None] * me
            else:
                s = sub6.shape[1]
                GK, GM = fem.fcm_tables(h, D, s)
                i, j, k = el[part].T
                chi = sub6[i, :, j, :, k, :].reshape(len(part), s ** 3)
                Kp = (chi @ GK).reshape(-1, 24, 24)
                Mp = (chi @ GM).reshape(-1, 24, 24)
            kind[part] = 1 + np.arange(len(part))
            Kloc = np.concatenate([ke[None], Kp])
            Mloc = np.concatenate([me[None], Mp])
        else:
            Kloc, Mloc = ke[None], me[None]
        self.Kloc, self.Mloc = Kloc, Mloc
        Nx, Ny, Nz = self.tiles
        L = np.array([Nx * n, Ny * n, Nz * n])
        self.L = L
        # global elements: every tile copy
        offs = np.array([[cx * n, cy * n, cz * n] for cz in range(Nz) for cy in range(Ny) for cx in range(Nx)])
        gel = (el[None, :, :] + offs[:, None, :]).reshape(-1, 3)
        gkind = np.tile(kind, len(offs))
        gw = np.tile(w, len(offs))
        nodes = gel[:, None, :] + OFF[None, :, :]       # (ne,8,3) node lattice coords
        P = L + np.array([0 if p else 1 for p in periodic])  # node planes per direction
        for d in range(3):
            if periodic[d]:
                nodes[..., d] %= L[d]
        lin = nodes[..., 0] + P[0] * (nodes[..., 1] + P[1] * nodes[..., 2])
        used, inv = np.unique(lin, return_inverse=True)
        inv = inv.reshape(lin.shape)
        self.node_lin = used
        self.node_ijk = np.stack([used % P[0], (used // P[0]) % P[1], used // (P[0] * P[1])], axis=1)
        self.nnode = len(used)
        self.ndof = 3 * self.nnode
        self.edof = (3 * inv[..., None] + np.arange(3)).reshape(len(gel), 24)
        self.el_ijk, self.el_kind, self.el_w = gel, gkind, gw
        self.ne = len(gel)
        self.K = self._assemble(Kloc)
        self.M = self._assemble(Mloc) if with_mass else None
        self.build_s = round(time.perf_counter() - t0, 2)

    def _assemble(self, loc):
        """CSR on ONE fixed pattern (the element connectivity; explicit zeros kept), so K and M share it."""
        N = self.ndof
        if not hasattr(self, "_scatter"):
            rows = np.repeat(self.edof, 24, axis=1).ravel()
            cols = np.tile(self.edof, (1, 24)).ravel()
            uniq, scatter = np.unique(rows * N + cols, return_inverse=True)
            del rows, cols
            r = uniq // N
            indptr = np.zeros(N + 1, np.int64)
            np.add.at(indptr, r + 1, 1)
            self._indptr = np.cumsum(indptr).astype(np.int32)
            self._indices = (uniq % N).astype(np.int32)
            self._scatter = scatter.astype(np.int64)
        nnz = len(self._indices)
        data = np.zeros(nnz)
        chunk = 100000
        for s0 in range(0, self.ne, chunk):
            vals = loc[self.el_kind[s0:s0 + chunk]].ravel()
            data += np.bincount(self._scatter[s0 * 576:(s0 + chunk) * 576], weights=vals, minlength=nnz)
        A = sp.csr_matrix((data, self._indices, self._indptr), shape=(N, N))
        A.has_sorted_indices = True
        return A

    @property
    def density(self):
        return float(self.el_w.sum() / np.prod(self.L))

    def face_nodes(self, axis: int, side: int) -> np.ndarray:
        """Node indices on the face axis = 0 (side 0) or axis = L (side 1) of the block."""
        val = 0 if side == 0 else self.L[axis]
        return np.flatnonzero(self.node_ijk[:, axis] == val)

    def face_weights(self, axis: int, side: int) -> tuple[np.ndarray, np.ndarray]:
        """Nodes of a face and their lumped solid face areas (each element touching the face gives coverage x
        h^2 / 4 to each of its 4 face nodes; cell units)."""
        h = 1.0 / self.n
        lay = 0 if side == 0 else self.L[axis] - 1
        e = np.flatnonzero(self.el_ijk[:, axis] == lay)
        loc = np.flatnonzero(OFF[:, axis] == (0 if side == 0 else 1))
        nd = self.edof[e][:, 3 * loc] // 3
        wts = np.repeat(self.el_w[e][:, None] * h * h / 4, 4, axis=1)
        idx, inv = np.unique(nd.ravel(), return_inverse=True)
        return idx, np.bincount(inv, weights=wts.ravel())


def cell_geometry(spec: dict, n: int):
    cov, sub6, info = geometry.design_cell(spec, n)
    return cov, sub6, info


# ------------------------------------------------------------------------------------------------------------
# static: block between two bonded rigid plates
# ------------------------------------------------------------------------------------------------------------
def plate_compression(mesh: TiledMesh, axis: int = 2, delta: float = 1e-3) -> dict:
    """Bottom face (axis = 0) fixed in all directions, top face (axis = L) displaced by delta along `axis`, its
    lateral displacement held at 0 (bonded rigid plates); other faces free (or periodic). Returns the reaction
    force F (sum over the top nodes, cell units, E_s = 1), k* = F / delta, the residual and timings."""
    t0 = time.perf_counter()
    bot, top = mesh.face_nodes(axis, 0), mesh.face_nodes(axis, 1)
    pres_n = np.concatenate([bot, top])
    pdof = (3 * pres_n[:, None] + np.arange(3)).ravel()
    up = np.zeros(mesh.ndof)
    up[3 * top + axis] = delta
    free = np.setdiff1d(np.arange(mesh.ndof), pdof)
    K = mesh.K
    Kff = K[free][:, free].tocsr()
    b = -(K[free][:, pdof] @ up[pdof])
    U = sp.triu(Kff, format="csr")
    U.sort_indices()
    s = Pardiso(mtype=2)
    st = s.factor(U)
    x = s.solve(b)
    s.free()
    res = float(np.linalg.norm(Kff @ x - b) / max(np.linalg.norm(b), 1e-300))
    u = up.copy()
    u[free] = x
    f = K @ u
    F = float(f[3 * top + axis].sum())
    Fb = float(f[3 * bot + axis].sum())
    return dict(F=F, F_bottom=Fb, k=F / delta, delta=delta, residual=res, n_perturbed=st["n_perturbed"],
                ndof=mesh.ndof, ne=mesh.ne, seconds=round(time.perf_counter() - t0, 2), build_s=mesh.build_s)


def cubic_C(E100: float, nu100: float, G: float) -> np.ndarray:
    """Cubic 6x6 stiffness (Voigt, engineering shear) from E100, nu100 and G = C44."""
    S = np.zeros((6, 6))
    S[:3, :3] = -nu100 / E100
    S[np.arange(3), np.arange(3)] = 1.0 / E100
    S[3:, 3:] = np.eye(3) / G
    return np.linalg.inv(S)


def homogenized_block(C: np.ndarray, tiles=(6, 6, 6), m: int = 4, axis: int = 2) -> dict:
    """Macro solve of a homogeneous block of tiles (cell units) with material C*, m hex8i elements per cell edge,
    between bonded rigid plates (plate_compression)."""
    cov = np.ones((m, m, m))
    mesh = TiledMesh(cov, None, tiles=tiles, periodic=(False, False, False), D=C, with_mass=False)
    r = plate_compression(mesh, axis=axis)
    r["m_per_cell"] = m
    return r


# ------------------------------------------------------------------------------------------------------------
# frequency domain: periodic slab (chain) with a driven bonded plate and a free far end
# ------------------------------------------------------------------------------------------------------------
class HarmonicChain:
    """6-cell chain along z, periodic in x and y (k_perp = 0). Input face z = 0: all nodes driven by a rigid,
    bonded plate with displacement U0 = 1 along `drive` (and 0 in the other two directions). Output face z = Nz:
    traction free. Damping: K* = (1 + i eta) K (hysteretic loss factor eta).

    Transmission T(f) = |u_out| / U0, u_out = the solid-area-weighted mean of the output-face displacement
    component along the drive direction (complex), so T(f -> 0) = 1 (0 dB). Solved on the real symmetric 2N form
    [[Ar, Ai], [Ai, -Ar]] [x_r; -x_i] = [b_r; b_i] (A = Ar + i Ai = (1 + i eta) K_ff - omega^2 M_ff) with PARDISO
    mtype -2; the symbolic factorization is reused over frequencies."""

    def __init__(self, mesh: TiledMesh, eta: float = 0.01, axis: int = 2):
        self.mesh, self.eta, self.axis = mesh, eta, axis
        bot = mesh.face_nodes(axis, 0)
        self.pdof = (3 * bot[:, None] + np.arange(3)).ravel()
        self.free = np.setdiff1d(np.arange(mesh.ndof), self.pdof)
        K, M = mesh.K, mesh.M
        f, p = self.free, self.pdof
        self.Kff = K[f][:, f].tocsr(); self.Kff.sort_indices()
        self.Mff = M[f][:, f].tocsr(); self.Mff.sort_indices()
        assert np.array_equal(self.Kff.indptr, self.Mff.indptr) and np.array_equal(self.Kff.indices, self.Mff.indices)
        self.Kfp = K[f][:, p].tocsr()
        self.Mfp = M[f][:, p].tocsr()
        self._pattern()
        top, wts = mesh.face_weights(axis, 1)
        self.out_nodes, self.out_w = top, wts / wts.sum()
        # position of each output node's dofs among the free dofs
        pos = -np.ones(mesh.ndof, np.int64)
        pos[self.free] = np.arange(len(self.free))
        self.out_pos = pos[3 * top[:, None] + np.arange(3)]  # (n_out, 3)
        assert (self.out_pos >= 0).all()
        self.solver = Pardiso(mtype=-2)
        self.nf = len(self.free)

    def _pattern(self):
        """CSR pattern of triu([[Ar, Ai], [Ai, -Ar]]) and the source map into the N x N data (as fem.real2n)."""
        A = self.Kff
        N = A.shape[0]
        rows = np.repeat(np.arange(N), np.diff(A.indptr))
        cols = A.indices
        e = np.arange(len(cols))
        up = cols >= rows
        R = np.concatenate([rows[up], rows, N + rows[up]])
        C = np.concatenate([cols[up], N + cols, N + cols[up]])
        src = np.concatenate([e[up], e, e[up]])
        part = np.concatenate([np.zeros(up.sum(), np.int8), np.ones(len(e), np.int8), 2 * np.ones(up.sum(), np.int8)])
        order = np.lexsort((C, R))
        R, C, src, part = R[order], C[order], src[order], part[order]
        indptr = np.zeros(2 * N + 1, np.int64)
        np.add.at(indptr, R + 1, 1)
        self.indptr = np.cumsum(indptr).astype(np.int32)
        self.indices = C.astype(np.int32)
        self.src, self.part = src, part

    def _S(self, sigma: float) -> sp.csr_matrix:
        Ar = self.Kff.data - sigma * self.Mff.data
        Ai = self.eta * self.Kff.data
        v = np.where(self.part == 0, Ar[self.src], np.where(self.part == 1, Ai[self.src], -Ar[self.src]))
        S = sp.csr_matrix((v, self.indices, self.indptr), shape=(2 * self.nf, 2 * self.nf), copy=False)
        S.has_sorted_indices = True
        return S

    def solve(self, f_stars, drives=(2, 0), log=None) -> dict:
        """Transmission at each f* for each drive direction (0 = x shear, 2 = z longitudinal)."""
        out = {d: [] for d in drives}
        info = dict(residual_max=0.0, perturbed_max=0, seconds=[])
        nu = self.mesh.nu
        for i, fs in enumerate(f_stars):
            t0 = time.perf_counter()
            sig = bloch.f_to_sigma(float(fs), nu)
            S = self._S(sig)
            st = self.solver.factor(S)
            B = np.zeros((2 * self.nf, len(drives)))
            for j, d in enumerate(drives):
                up = np.zeros(len(self.pdof))
                up[d::3] = 1.0                      # every bottom node, component d, U0 = 1
                br = -(self.Kfp @ up - sig * (self.Mfp @ up))
                bi = -(self.eta * (self.Kfp @ up))
                B[:, j] = np.concatenate([br, bi])
            X = self.solver.solve(B)
            res = np.linalg.norm(S @ X - B, axis=0) / np.maximum(np.linalg.norm(B, axis=0), 1e-300)
            # S here is the upper triangle only: the residual of the full symmetric operator is needed
            Sf = S + sp.triu(S, k=1).T
            res = np.linalg.norm(Sf @ X - B, axis=0) / np.maximum(np.linalg.norm(B, axis=0), 1e-300)
            for j, d in enumerate(drives):
                xr, xi = X[:self.nf, j], -X[self.nf:, j]
                u = xr + 1j * xi
                uo = u[self.out_pos[:, d]]
                out[d].append(complex(np.sum(self.out_w * uo)))
            info["residual_max"] = max(info["residual_max"], float(res.max()))
            info["perturbed_max"] = max(info["perturbed_max"], int(st["n_perturbed"]))
            info["seconds"].append(round(time.perf_counter() - t0, 2))
            if log and (i % 10 == 0 or i == len(f_stars) - 1):
                log(f"    f*={fs:.4f} ({i + 1}/{len(f_stars)}) T_z={abs(out[drives[0]][-1]):.3e} res={res.max():.1e} "
                    f"pert={st['n_perturbed']} {info['seconds'][-1]:.1f}s")
        self.solver.free()
        return dict(f_star=[float(x) for x in f_stars],
                    T={str(d): [abs(c) for c in v] for d, v in out.items()},
                    u_out={str(d): [[c.real, c.imag] for c in v] for d, v in out.items()},
                    residual_max=info["residual_max"], perturbed_max=info["perturbed_max"],
                    seconds_total=round(float(np.sum(info["seconds"])), 1), ndof_free=self.nf,
                    ne=self.mesh.ne, eta=self.eta)
