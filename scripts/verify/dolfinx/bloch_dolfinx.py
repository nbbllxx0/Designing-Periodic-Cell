r"""Third-party elastic Bloch (Floquet) bands with DOLFINx 0.11 + dolfinx_mpc 0.11 (complex PETSc, SLEPc).

Runs INSIDE the container `amm/dolfinx-mpc:0.11.0-complex` (V1c, results/verification/dolfinx/NOTES.md).
No amm code is imported here: geometry arrives as numbers (box parameters or the exported sub-sample occupancy).

Model (E = 1, rho = 1, Poisson ratio nu; frequencies reported as f* = f a / c_t, c_t = sqrt(mu / rho), a = 1):
  find u in V_h, omega^2:  int sigma(u) : conj(eps(v)) chi dx = omega^2 int u . conj(v) chi dx   for all v,
  with Floquet-periodic constraints u(x + e_d) = exp(i k_d) u(x) imposed by dolfinx_mpc
  MultiPointConstraint.create_periodic_constraint_geometrical (one call per wrap vector w in {0,1}^3 \ 0, complex
  scale exp(i k . w); every master has all coordinates < 1, so no master is itself a slave).

Geometry models (`--model`):
  exact     cube_bars only: the exact union of boxes on a conforming tensor grid whose breakpoints include every face
            of the geometry (chi = 1 on every cell); Lagrange Q`deg`. Rayleigh-Ritz: each band is an upper bound of
            the continuum band at that k.
  fcm       the cell's exported sub-sample occupancy (n, s, n, s, n, s) on a uniform n^3 grid (cells with zero
            coverage removed); full cells integrated exactly, partial cells with a tensor Gauss rule of `--qsub`
            points per direction on each of the s^3 sub-cubes, chi = sub-sample value (finite-cell integration).
  fcm_id    identity model for Q1: partial cells with the one-point midpoint rule on each sub-cube (the rule amm
            uses), full cells exact. With deg 1 this is the same discrete model as amm's hex8 + finite-cell mesh.

Modes:
  eval    eigenvalues at a list of k (`--ks` JSON list of [kx, ky, kz] in rad / a); `--split` lets every MPI rank
          solve its own k on COMM_SELF (small problems), otherwise all ranks solve one k together (MUMPS in parallel).
  search  dense irreducible-zone scan (path, 8 points per leg, plus `--n-random` uniform interior points) and a
          26-direction pattern search (step 0.15 pi halved each round) maximizing band nb and minimizing band nb+1,
          using split mode. Independent of amm's own adversarial search (different seed, code and model).

Output: JSON with one record per k: k, bands f* (lowest `--nev`), relative residuals, solve time, ndof.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import time

import numpy as np
from mpi4py import MPI

import basix.ufl
import dolfinx
import dolfinx_mpc
import ufl
from dolfinx import fem
from petsc4py import PETSc
from slepc4py import SLEPc

WRAPS = [np.array(w, float) for w in itertools.product((0, 1), repeat=3) if any(w)]
TOL = 1e-9


def c_t(nu):
    return float(np.sqrt(1.0 / (2 * (1 + nu))))


# ---------------------------------------------------------------- meshes
def _tensor_mesh(comm, axes, solid):
    """axes: three 1D node arrays; solid: bool (nx, ny, nz) per cell. Returns a hex mesh of the solid cells."""
    if comm.rank == 0:
        nx, ny, nz = (len(a) - 1 for a in axes)
        el = np.argwhere(solid)
        off = np.array([[(a >> 0) & 1, (a >> 1) & 1, (a >> 2) & 1] for a in range(8)])  # DOLFINx hex vertex order
        nodes = el[:, None, :] + off[None]
        lin = nodes[..., 0] + (nx + 1) * (nodes[..., 1] + (ny + 1) * nodes[..., 2])
        used, inv = np.unique(lin, return_inverse=True)
        cells = inv.reshape(lin.shape).astype(np.int64)
        i = used % (nx + 1)
        j = (used // (nx + 1)) % (ny + 1)
        k = used // ((nx + 1) * (ny + 1))
        x = np.stack([axes[0][i], axes[1][j], axes[2][k]], axis=1)
        cell_ijk = el
    else:
        cells, x, cell_ijk = np.zeros((0, 8), np.int64), np.zeros((0, 3)), np.zeros((0, 3), np.int64)
    ce = basix.ufl.element("Lagrange", "hexahedron", 1, shape=(3,))
    msh = dolfinx.mesh.create_mesh(comm, cells, ce, x)
    return msh, cell_ijk


def cube_bars_axes(c, w, n):
    """Per-axis breakpoints of the cube-and-bars cell, each segment split into round(len * n) cells (>= 1)."""
    b = np.unique(np.round([0.0, (1 - c) / 2, (1 - w) / 2, (1 + w) / 2, (1 + c) / 2, 1.0], 12))
    pts = [0.0]
    for a, bb in zip(b[:-1], b[1:]):
        m = max(1, int(round((bb - a) * n)))
        pts += list(np.linspace(a, bb, m + 1)[1:])
    return np.array(pts)


def exact_cube_bars(comm, c, w, n):
    ax = cube_bars_axes(c, w, n)
    ctr = 0.5 * (ax[:-1] + ax[1:]) - 0.5
    X, Y, Z = np.meshgrid(ctr, ctr, ctr, indexing="ij")
    A = [np.abs(X), np.abs(Y), np.abs(Z)]
    core = (A[0] <= c / 2) & (A[1] <= c / 2) & (A[2] <= c / 2)
    bars = ((A[1] <= w / 2) & (A[2] <= w / 2)) | ((A[0] <= w / 2) & (A[2] <= w / 2)) | ((A[0] <= w / 2) & (A[1] <= w / 2))
    msh, _ = _tensor_mesh(comm, [ax] * 3, core | bars)
    return msh, dict(h_max=float(np.diff(ax).max()), h_min=float(np.diff(ax).min()), cells_per_axis=len(ax) - 1)


# ---------------------------------------------------------------- problem
class BlochProblem:
    def __init__(self, comm, args, case):
        self.comm, self.args, self.case = comm, args, case
        nu = case["nu"]
        self.nu = nu
        t0 = time.perf_counter()
        info = {}
        chi_parts = None
        if args.model == "exact":
            g = case["geometry"]
            assert g["kind"] == "cube_bars", "exact model only for cube_bars"
            msh, info = exact_cube_bars(comm, g["c"], g["w"], args.n)
        else:
            d = np.load(case["fcm"][str(args.n)])
            cov, sub = d["cov"], d["sub"]
            n = cov.shape[0]
            assert n == args.n
            ax = np.linspace(0, 1, n + 1)
            msh, cell_ijk = _tensor_mesh(comm, [ax] * 3, cov > 0)
            info = dict(h_max=1.0 / n, h_min=1.0 / n, cells_per_axis=n, s=int(sub.shape[1]))
            chi_parts = (cov, sub)
        self.msh = msh
        tdim = 3
        ncell = msh.topology.index_map(tdim).size_local + msh.topology.index_map(tdim).num_ghosts
        deg = args.deg
        self.V = fem.functionspace(msh, ("Lagrange", deg, (3,)))
        u, v = ufl.TrialFunction(self.V), ufl.TestFunction(self.V)
        lam = nu / ((1 + nu) * (1 - 2 * nu))
        mu = 1.0 / (2 * (1 + nu))

        def eps(z):
            return ufl.sym(ufl.grad(z))

        def sig(z):
            return 2 * mu * eps(z) + lam * ufl.tr(eps(z)) * ufl.Identity(3)

        ak = ufl.inner(sig(u), eps(v))
        am = ufl.inner(u, v)
        qdeg = 2 * deg + 2  # exact for the full-cell integrands on affine hexes (and then some)
        if chi_parts is None:
            dx = ufl.dx(domain=msh, metadata={"quadrature_degree": qdeg})
            self.a_form, self.m_form = fem.form(ak * dx), fem.form(am * dx)
            info["n_partial"] = 0
        else:
            cov, sub = chi_parts
            s = sub.shape[1]
            # original (input) index of every local cell -> its voxel (i, j, k); same order on all ranks via the
            # mesh's original_cell_index into the rank-0 argwhere list, rebuilt identically here
            el = np.argwhere(cov > 0)
            orig = np.asarray(msh.topology.original_cell_index)[:ncell]
            ijk = el[orig]
            full = cov[ijk[:, 0], ijk[:, 1], ijk[:, 2]] >= 1.0 - 1e-12
            tags = np.where(full, 1, 2).astype(np.int32)
            ct = dolfinx.mesh.meshtags(msh, tdim, np.arange(ncell, dtype=np.int32), tags)
            # sub-cube quadrature on the reference cell [0,1]^3
            if args.model == "fcm_id":
                g1, gw = np.array([0.5]), np.array([1.0])
            else:
                g1, gw = np.polynomial.legendre.leggauss(args.qsub)
                g1, gw = 0.5 * (g1 + 1), 0.5 * gw
            c1 = (np.arange(s)[:, None] + g1[None, :]).ravel() / s  # points per direction
            w1 = np.tile(gw, s) / s
            sub_of = np.repeat(np.arange(s), len(g1))  # sub-cube index of each 1D point
            P = np.array(list(itertools.product(range(len(c1)), repeat=3)))  # (a, b, c) index triples
            pts = np.stack([c1[P[:, 0]], c1[P[:, 1]], c1[P[:, 2]]], axis=1)
            wts = w1[P[:, 0]] * w1[P[:, 1]] * w1[P[:, 2]]
            qe = basix.ufl.quadrature_element("hexahedron", value_shape=(), points=pts, weights=wts)
            Vq = fem.functionspace(msh, qe)
            chi = fem.Function(Vq)
            # physical coordinates of the quadrature points (robust to any vertex reordering)
            xe = fem.Expression(ufl.SpatialCoordinate(msh), pts)
            cells = np.arange(ncell, dtype=np.int32)
            X = xe.eval(msh, cells).reshape(ncell, len(pts), 3).real
            nf = n * s
            idx = np.clip(np.floor(X * nf).astype(np.int64), 0, nf - 1)
            sub_flat = sub.reshape(nf, nf, nf) if sub.shape == (n, s, n, s, n, s) else None
            # sub is (n, s, n, s, n, s): fine index along x = i*s + a
            vals = sub.reshape(n * s, n * s, n * s)[idx[..., 0], idx[..., 1], idx[..., 2]]
            # check that the point lies in its own voxel
            vox = idx // s
            assert np.all(vox == ijk[:, None, :]), "quadrature point outside its voxel"
            dofs = Vq.dofmap.list[:ncell]
            chi.x.array[dofs.ravel()] = vals.ravel()
            chi.x.scatter_forward()
            del sub_flat
            dxm = ufl.Measure("dx", domain=msh, subdomain_data=ct)
            self.a_form = fem.form(ak * dxm(1, metadata={"quadrature_degree": qdeg}) + chi * ak * dxm(2))
            self.m_form = fem.form(am * dxm(1, metadata={"quadrature_degree": qdeg}) + chi * am * dxm(2))
            info["n_partial"] = int(comm.allreduce(int((~full[: msh.topology.index_map(tdim).size_local]).sum())))
            info["qpts_partial"] = int(len(pts))
        info["n_cells"] = int(comm.allreduce(msh.topology.index_map(tdim).size_local))
        info["setup_s"] = round(time.perf_counter() - t0, 2)
        self.info = info
        # dof coordinates for the presence test of masters
        xd = self.V.tabulate_dof_coordinates()
        allx = comm.allgather(np.round(xd, 9))
        self.present = set(map(tuple, np.concatenate(allx)))
        # serial fast path: the k-independent K0, M0 assembled once; per k, K = P^H K0 P with the constraint matrix
        # P built from dolfinx_mpc's own slave/master/coefficient data (validated against dolfinx_mpc.assemble_matrix
        # with --validate-fast; deviation 2 in NOTES.md)
        self.K0 = self.M0 = None
        if comm.size == 1 and not args.no_fast:
            import dolfinx.fem.petsc as fp
            import scipy.sparse as sps
            t1 = time.perf_counter()
            mats = []
            for form in (self.a_form, self.m_form):
                A = fp.assemble_matrix(form)
                A.assemble()
                ai, aj, av = A.getValuesCSR()
                mats.append(sps.csr_matrix((av, aj, ai), shape=A.getSize()))
                A.destroy()
            self.K0, self.M0 = mats
            info["asm0_s"] = round(time.perf_counter() - t1, 2)

    def _indicator(self, w):
        def ind(x):
            ok = np.ones(x.shape[1], bool)
            for d in range(3):
                if w[d]:
                    ok &= np.abs(x[d] - 1.0) < TOL
                else:
                    ok &= x[d] < 1.0 - TOL
            if ok.any():  # every slave must have its master in the mesh (cells here are mirror-symmetric)
                img = np.round((x[:, ok] - w[:, None]).T, 9)
                miss = [tuple(p) for p in img if tuple(p) not in self.present]
                if miss:
                    raise RuntimeError(f"{len(miss)} slaves without master, e.g. {miss[:2]}")
            return ok
        return ind

    def _fast_mats(self, mpc):
        """P^H K0 P and P^H M0 P (slave rows/columns zero, slave diagonal 1 and 1e-8, as dolfinx_mpc assembles)."""
        import scipy.sparse as sps
        N = self.K0.shape[0]
        slaves = np.asarray(mpc.slaves, dtype=np.int64)
        ca, co = (np.asarray(x) for x in mpc.coefficients())
        masters = mpc.masters
        off = np.asarray(masters.offsets)
        mlist = np.asarray(masters.array, dtype=np.int64)
        assert len(off) == N + 1 and np.array_equal(off, co), (len(off), N)  # per-dof adjacency, same layout
        is_slave = np.zeros(N, bool)
        is_slave[slaves] = True
        free = np.flatnonzero(~is_slave)
        sel = np.concatenate([np.arange(off[s], off[s + 1]) for s in slaves]) if len(slaves) else np.zeros(0, int)
        cnt = off[slaves + 1] - off[slaves]
        assert np.all(cnt >= 1) and not is_slave[mlist[sel]].any(), "a slave without master, or a slave master"
        rows = np.concatenate([free, np.repeat(slaves, cnt)])
        cols = np.concatenate([free, mlist[sel]])
        vals = np.concatenate([np.ones(len(free), complex), ca[sel]])
        P = sps.csr_matrix((vals, (rows, cols)), shape=(N, N))
        PH = P.conj().T.tocsr()
        out = []
        for A0, dv in ((self.K0, 1.0), (self.M0, 1e-8)):
            A = (PH @ A0 @ P).tocsr()
            A = A + sps.diags(np.where(is_slave, dv, 0.0).astype(complex))
            A = 0.5 * (A + A.conj().T)
            A = A.tocsr()
            A.sort_indices()
            m = PETSc.Mat().createAIJ(size=A.shape, csr=(A.indptr.astype(PETSc.IntType), A.indices.astype(PETSc.IntType), A.data),
                                      comm=MPI.COMM_SELF)
            m.assemble()
            out.append(m)
        return out

    def solve(self, k, nev):
        t0 = time.perf_counter()
        k = np.asarray(k, float)
        mpc = dolfinx_mpc.MultiPointConstraint(self.V)
        for w in WRAPS:
            scale = PETSc.ScalarType(np.exp(1j * float(k @ w)))
            mpc.create_periodic_constraint_geometrical(self.V, self._indicator(w), lambda x, w=w: x - w[:, None],
                                                       [], scale, tol=1e-9)
        mpc.finalize()
        t1 = time.perf_counter()
        fast = self.K0 is not None
        if not fast or self.args.validate_fast:
            K = dolfinx_mpc.assemble_matrix(self.a_form, mpc, bcs=[], diagval=1.0)
            K.assemble()
            M = dolfinx_mpc.assemble_matrix(self.m_form, mpc, bcs=[], diagval=1e-8)  # slave rows: lambda = 1e8
            M.assemble()
        fast_err = None
        if fast:
            Kf, Mf = self._fast_mats(mpc)
            if self.args.validate_fast:
                import scipy.sparse as sps
                errs = []
                for A, B in ((K, Kf), (M, Mf)):
                    ai, aj, av = A.getValuesCSR()
                    As = sps.csr_matrix((av, aj, ai), shape=A.getSize())
                    bi, bj, bv = B.getValuesCSR()
                    Bs = sps.csr_matrix((bv, bj, bi), shape=B.getSize())
                    errs.append(float(abs(As - Bs).max() / abs(As).max()))
                fast_err = max(errs)
                K.destroy(); M.destroy()
            K, M = Kf, Mf
        t2 = time.perf_counter()
        n_slaves = self.comm.allreduce(mpc.num_local_slaves)
        ndof_full = self.V.dofmap.index_map.size_global * 3
        if self.args.eps_type == "block":
            lam, res, nconv = block_eigs(K, M, nev, self.comm)
        else:
            lam, res, nconv = slepc_eigs(K, M, nev, self.comm, self.args.eps_type)
        f = np.sqrt(np.clip(lam, 0, None)) / (2 * np.pi * c_t(self.nu))
        herm, dense = None, None
        if (self.args.check_hermitian or self.args.dense_check) and self.comm.size == 1:
            import scipy.linalg as sla
            import scipy.sparse as sps
            ai, aj, av = K.getValuesCSR()
            Ks = sps.csr_matrix((av, aj, ai), shape=K.getSize())
            herm = float(abs(Ks - Ks.conj().T).max() / abs(Ks).max())
            if self.args.dense_check:  # all eigenvalues of the reduced (non-slave) pencil, dense LAPACK
                bi, bj, bv = M.getValuesCSR()
                Ms = sps.csr_matrix((bv, bj, bi), shape=M.getSize())
                keep = np.setdiff1d(np.arange(Ks.shape[0]), np.asarray(mpc.slaves))
                w = sla.eigh(Ks[keep][:, keep].toarray(), Ms[keep][:, keep].toarray(), eigvals_only=True)
                dense = (np.sqrt(np.clip(w[:nev], 0, None)) / (2 * np.pi * c_t(self.nu))).tolist()
        out = dict(k=k.tolist(), f=f.tolist(), lam=lam.tolist(), rel_res=res.tolist(), iters_or_nconv=int(nconv),
                   ndof=int(ndof_full - 3 * 0 - n_slaves), n_slaves=int(n_slaves), ndof_unconstrained=int(ndof_full),
                   t_mpc=round(t1 - t0, 2), t_asm=round(t2 - t1, 2), t_eig=round(time.perf_counter() - t2, 2),
                   hermitian_err=herm, dense_f=dense, eps_type=self.args.eps_type, fast_path=bool(fast),
                   fast_vs_mpc_rel_err=fast_err)
        K.destroy(); M.destroy()
        return out


SIGMA = -1e-2  # shift (omega^2 units) just below the rigid-body modes: the lowest eigenvalues are wanted


def slepc_eigs(K, M, nev, comm, eps_type):
    """SLEPc shift-invert (subspace iteration or Krylov-Schur), MUMPS LU."""
    eps = SLEPc.EPS().create(comm)
    eps.setOperators(K, M)
    eps.setProblemType(SLEPc.EPS.ProblemType.GHEP)
    eps.setType(eps_type)
    eps.setDimensions(nev, max(2 * nev + 10, 40))
    eps.setTarget(SIGMA)
    eps.setWhichEigenpairs(SLEPc.EPS.Which.TARGET_MAGNITUDE)
    st = eps.getST()
    st.setType(SLEPc.ST.Type.SINVERT)
    st.setShift(SIGMA)
    ksp = st.getKSP()
    ksp.setType("preonly")
    pc = ksp.getPC()
    pc.setType("lu")
    pc.setFactorSolverType("mumps")
    eps.setTolerances(1e-11, 300)
    eps.setFromOptions()
    eps.solve()
    nconv = eps.getConverged()
    lam, res = [], []
    for i in range(nconv):
        lam.append(eps.getEigenvalue(i).real)
        res.append(eps.computeError(i, SLEPc.EPS.ErrorType.RELATIVE))
    order = np.argsort(lam)
    eps.destroy()
    return np.array(lam)[order][:nev], np.array(res)[order][:nev], int(nconv)


def block_eigs(K, M, nev, comm, extra=8, m=4, rtol=1e-8, maxit=60, seed=7):
    """Restarted block Krylov method with Rayleigh-Ritz on the shift-invert operator (K - sigma M)^-1 M: a block of
    nev + extra random vectors, m block powers per restart, M-orthonormalized;  MUMPS LU of K - sigma M with multi-RHS solves (PETSc MatMatSolve). A block method finds every copy
    of a degenerate eigenvalue as long as the block is wider than the multiplicity; single-vector Krylov-Schur
    did not (sanity test). Stops when every relative residual |K x - lam M x| / |K x| of the nev lowest Ritz pairs
    is <= rtol (eigenvalue error then of order rtol^2)."""
    A = K.copy()
    A.axpy(-SIGMA, M, structure=PETSc.Mat.Structure.SUBSET_NONZERO_PATTERN)
    ksp = PETSc.KSP().create(comm)
    ksp.setOperators(A)
    ksp.setType("preonly")
    pc = ksp.getPC()
    pc.setType("lu")
    pc.setFactorSolverType("mumps")
    ksp.setUp()
    F = pc.getFactorMatrix()
    p = nev + extra
    r0, r1 = K.getOwnershipRange()
    nloc, N = r1 - r0, K.getSize()[0]

    def dense(arr=None):
        D = PETSc.Mat().createDense(((nloc, N), (p, p)), comm=comm)
        D.setUp()
        if arr is not None:
            D.getDenseArray()[:] = arr
        D.assemble()
        return D

    rng = np.random.default_rng(seed + r0)
    X = rng.standard_normal((nloc, p)) + 1j * rng.standard_normal((nloc, p))
    import scipy.linalg as sla
    Xm, Bm, Ym, Kd, Md = dense(), dense(), dense(), dense(), dense()

    def residuals(X, lam):
        Xm.getDenseArray()[:] = X
        K.matMult(Xm, Kd)
        M.matMult(Xm, Md)
        kx, mx = Kd.getDenseArray(), Md.getDenseArray()
        R = comm.allreduce((np.abs(kx[:, :nev] - mx[:, :nev] * lam[None, :nev]) ** 2).sum(axis=0))
        Q = comm.allreduce((np.abs(kx[:, :nev]) ** 2).sum(axis=0))
        return np.sqrt(R) / np.maximum(np.sqrt(Q), 1e-300)

    def op(X):  # (K - sigma M)^-1 M X, one multi-RHS MUMPS solve
        Xm.getDenseArray()[:] = X
        M.matMult(Xm, Bm)
        F.matSolve(Bm, Ym)
        return Ym.getDenseArray().copy()

    def apply(Mat, X):  # Mat @ X for any number of columns
        q = X.shape[1]
        A1 = PETSc.Mat().createDense(((nloc, N), (q, q)), comm=comm)
        A1.setUp()
        A1.getDenseArray()[:] = X
        A1.assemble()
        B1 = Mat.matMult(A1)
        out = B1.getDenseArray().copy()
        A1.destroy(); B1.destroy()
        return out

    def morth(Z, Qs, MQs):
        """M-orthonormalize the block Z against the blocks Qs (twice) and within itself (drops dependent columns)."""
        for _ in range(2):
            for Qb, MQb in zip(Qs, MQs):
                Z = Z - Qb @ comm.allreduce(MQb.conj().T @ Z)
        MZ = apply(M, Z)
        G = comm.allreduce(Z.conj().T @ MZ)
        G = 0.5 * (G + G.conj().T)
        g, U = np.linalg.eigh(G)
        keep = g > 1e-10 * max(g.max(), 1e-300)
        W = U[:, keep] / np.sqrt(g[keep])
        return Z @ W, MZ @ W

    lam, res, hist = None, None, []
    for it in range(maxit):  # restarted block Krylov: span[X, Op X, ..., Op^(m-1) X], Rayleigh-Ritz, keep p vectors
        Qb, MQb = morth(X, [], [])
        Qs, MQs = [Qb], [MQb]
        for _ in range(m - 1):
            Z, MZ = morth(op(Qs[-1]) if Qs[-1].shape[1] == p else op(np.hstack([Qs[-1], np.zeros((nloc, p - Qs[-1].shape[1]))])),
                          Qs, MQs)
            if Z.shape[1] == 0:
                break
            Qs.append(Z); MQs.append(MZ)
        Q = np.hstack(Qs)
        KQ = apply(K, Q)
        H = comm.allreduce(Q.conj().T @ KQ)
        H = 0.5 * (H + H.conj().T)
        lam_all, V = np.linalg.eigh(H)
        lam = lam_all[:p]
        X = Q @ V[:, :p]
        res = residuals(X, lam)
        rmax = float(np.max(np.where(np.abs(lam[:nev]) < 1e-9, 0.0, res)))
        hist.append(rmax)
        if rmax <= rtol:
            break
        if len(hist) > 6 and rmax <= 1e-7 and rmax > 0.7 * hist[-4]:  # stagnated at the round-off floor
            break
    res = residuals(X, lam)
    for D in (Xm, Bm, Ym, Kd, Md, A):
        D.destroy()
    ksp.destroy()
    return lam[:nev], res, int(it + 1)


# ---------------------------------------------------------------- k sets
SC = {"G": (0, 0, 0), "X": (1, 0, 0), "M": (1, 1, 0), "R": (1, 1, 1)}


def kpath(m, path=("G", "X", "M", "G", "R", "X")):
    P = {k: np.pi * np.array(v, float) for k, v in SC.items()}
    ks = []
    for a, b in zip(path[:-1], path[1:]):
        for t in np.linspace(0, 1, m, endpoint=False):
            ks.append(P[a] + t * (P[b] - P[a]))
    ks.append(P[path[-1]])
    return np.array(ks)


def to_ibz(k):
    k = np.mod(np.asarray(k, float) + np.pi, 2 * np.pi) - np.pi
    return np.ascontiguousarray(np.sort(np.abs(k), axis=-1)[..., ::-1])


DIRS = np.array([d for d in np.ndindex(3, 3, 3) if d != (1, 1, 1)], float) - 1.0
DIRS /= np.linalg.norm(DIRS, axis=1, keepdims=True)


def split_eval(prob, ks, nev, comm):
    """Every rank solves its share of ks on its own (prob built on COMM_SELF); results gathered on all ranks."""
    mine = [(i, prob.solve(ks[i], nev)) for i in range(comm.rank, len(ks), comm.size)]
    allr = comm.allgather(mine)
    res = [None] * len(ks)
    for part in allr:
        for i, r in part:
            res[i] = r
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--model", choices=["exact", "fcm", "fcm_id"], required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--deg", type=int, default=2)
    ap.add_argument("--qsub", type=int, default=2)
    ap.add_argument("--mode", choices=["eval", "search"], default="eval")
    ap.add_argument("--ks", help="JSON file with a list of k (rad/a), or an inline JSON list")
    ap.add_argument("--nev", type=int, default=None)
    ap.add_argument("--split", action="store_true")
    ap.add_argument("--n-random", type=int, default=100)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--seed", type=int, default=20261107)
    ap.add_argument("--check-hermitian", action="store_true")
    ap.add_argument("--no-fast", action="store_true", help="serial runs: assemble with dolfinx_mpc at every k")
    ap.add_argument("--validate-fast", action="store_true", help="compare the fast path with dolfinx_mpc.assemble_matrix")
    ap.add_argument("--dense-check", action="store_true", help="small serial problems: dense eigh of the pencil")
    ap.add_argument("--eps-type", default="block", choices=["block", "subspace", "krylovschur"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    world = MPI.COMM_WORLD
    case = json.load(open(args.case))
    nb = case["below_band"]
    nev = args.nev or nb + 4
    split = args.split or args.mode == "search"
    comm = MPI.COMM_SELF if split else world
    t0 = time.perf_counter()
    prob = BlochProblem(comm, args, case)
    meta = dict(case=case["name"], model=args.model, n=args.n, deg=args.deg, qsub=args.qsub, nev=nev,
                below_band=nb, mesh=prob.info, ranks=world.size, split=split,
                versions=dict(dolfinx=dolfinx.__version__, petsc=PETSc.Sys.getVersion(),
                              slepc=SLEPc.Sys.getVersion(), scalar=str(PETSc.ScalarType)))
    if args.mode == "eval":
        ks = json.load(open(args.ks)) if os.path.exists(args.ks) else json.loads(args.ks)
        ks = np.asarray(ks, float).reshape(-1, 3)
        if split:
            res = split_eval(prob, ks, nev, world)
        else:
            res = []
            for k in ks:
                res.append(prob.solve(k, nev))
                if world.rank == 0:
                    print(f"k/pi={np.round(k / np.pi, 4).tolist()} f[nb-1:nb+1]={res[-1]['f'][nb - 1:nb + 1]} "
                          f"t={res[-1]['t_mpc'] + res[-1]['t_asm'] + res[-1]['t_eig']:.1f}s", flush=True)
        out = dict(meta, records=res)
    else:  # search
        rng = np.random.default_rng(args.seed)
        ks = np.vstack([kpath(8), np.sort(rng.uniform(0, np.pi, (args.n_random, 3)), axis=1)[:, ::-1]])
        res = split_eval(prob, ks, nev, world)
        F = np.array([r["f"] for r in res])
        hist = [dict(stage="dense", n=len(ks))]
        found = {}
        for band, sgn, name in ((nb - 1, -1.0, "lo"), (nb, 1.0, "hi")):
            order = np.argsort(sgn * F[:, band])[: args.top]
            cur, val = ks[order].copy(), F[order, band].copy()
            step = 0.15 * np.pi
            for r in range(args.rounds):
                trial = to_ibz((cur[:, None, :] + step * DIRS[None]).reshape(-1, 3))
                tr = split_eval(prob, trial, nev, world)
                res += tr
                ft = np.array([x["f"][band] for x in tr]).reshape(len(cur), -1)
                pick = np.argmin(sgn * ft, axis=1)
                better = sgn * ft[np.arange(len(cur)), pick] < sgn * val
                cur[better] = trial.reshape(len(cur), -1, 3)[better, pick[better]]
                val[better] = ft[better, pick[better]]
                hist.append(dict(stage=f"{name} round {r}", step_over_pi=step / np.pi, best=float(sgn * min(sgn * val))))
                step /= 2
            found[name] = dict(ks=cur.tolist(), vals=val.tolist(),
                               best_k=cur[np.argmin(sgn * val)].tolist(), best=float(val[np.argmin(sgn * val)]))
        out = dict(meta, records=res, search=found, history=hist,
                   dense_edges=[float(F[:, nb - 1].max()), float(F[:, nb].min())])
    out["seconds"] = round(time.perf_counter() - t0, 1)
    if world.rank == 0:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        json.dump(out, open(args.out, "w"), indent=1)
        print(f"wrote {args.out} ({out['seconds']} s)", flush=True)


if __name__ == "__main__":
    main()
