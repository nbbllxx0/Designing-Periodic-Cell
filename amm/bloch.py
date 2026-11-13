"""Elastic Bloch-wave bands of a periodic voxel cell: GPU search tier and inertia-count gap certificate.

Search tier: dense generalized Hermitian eigenproblems assembled directly on the GPU and solved in a batch over
k-points (complex64 by default). Fast, approximate, used inside design loops.

Certificate tier: for a claimed gap [f_lo, f_hi] above band j, factor K(k) - s M(k) in FP64 with PARDISO
(symmetric indefinite LDL^T on the real 2N form) at s = w(f_lo)^2 and s = w(f_hi)^2. By Sylvester's law of
inertia, the number of negative pivots equals the number of eigenvalues below s (each counted twice in the 2N
form). The gap holds at that k exactly when both counts equal j. Counts are trusted only with zero perturbed
pivots. This is evaluated on the irreducible-zone path plus random interior points, at two resolutions.
"""
from __future__ import annotations

import time

import numpy as np
import scipy.sparse as sp

from . import fem
from .pardiso import Pardiso
from .progress import checkpoint

NU_DEFAULT = 0.3


def c_t(E: float = 1.0, nu: float = NU_DEFAULT, rho: float = 1.0) -> float:
    return float(np.sqrt(E / (2 * (1 + nu)) / rho))


def f_to_sigma(f_star: float, nu: float = NU_DEFAULT) -> float:
    return float((2 * np.pi * c_t(nu=nu) * f_star) ** 2)


# ---------------- k-point sets (simple cubic lattice, a = 1) -----------------
SC_POINTS = {"G": (0, 0, 0), "X": (1, 0, 0), "M": (1, 1, 0), "R": (1, 1, 1)}
SC_PATH = ("G", "X", "M", "G", "R", "X")


def kpath(npts_per_leg: int = 8, path=SC_PATH) -> tuple[np.ndarray, list]:
    P = {k: np.pi * np.array(v, float) for k, v in SC_POINTS.items()}
    ks, ticks = [], []
    for a, b in zip(path[:-1], path[1:]):
        ticks.append((len(ks), a))
        for t in np.linspace(0, 1, npts_per_leg, endpoint=False):
            ks.append(P[a] + t * (P[b] - P[a]))
    ticks.append((len(ks), path[-1]))
    ks.append(P[path[-1]])
    return np.array(ks), ticks


def ibz_interior(n: int, seed: int = 0) -> np.ndarray:
    """Uniform random points in the simple-cubic irreducible wedge 0 <= kz <= ky <= kx <= pi."""
    rng = np.random.default_rng(seed)
    k = np.sort(rng.uniform(0, np.pi, size=(n, 3)), axis=1)[:, ::-1]
    return k


# ---------------- search tier (GPU dense) -----------------
def resolve_device(device: str = "cuda") -> str:
    """The torch device for the search tier: "cuda" when requested and available, else "cpu" (CPU fallback, B3
    2026-11-07; results are then not bit-identical to the GPU path). Other values pass through."""
    if device != "cuda":
        return device
    try:
        import torch
    except ImportError as e:
        raise ImportError("the search-tier Bloch solver needs PyTorch (pip install torch)") from e
    return "cuda" if torch.cuda.is_available() else "cpu"


class GPUBands:
    """Holds the torch-side copies of one mesh; call with k-points to get f* bands."""

    def __init__(self, mesh: fem.CellMesh, device: str = "cuda", dtype=None):
        import torch

        self.torch = torch
        self.mesh = mesh
        self.nu = mesh.nu
        self.dev = device
        self.dtype = dtype or torch.complex64
        rdt = torch.float32 if self.dtype == torch.complex64 else torch.float64
        self.ke = torch.tensor(mesh.Ke, device=device, dtype=rdt)  # (ne,24,24)
        self.me = torch.tensor(mesh.Me, device=device, dtype=rdt)
        N = mesh.ndof
        rows = np.repeat(mesh.edof, 24, axis=1).ravel()
        cols = np.tile(mesh.edof, (1, 24)).ravel()
        lin = rows.astype(np.int64) * N + cols
        # deterministic assembly: every global entry sums its element contributions in a fixed order (a gather
        # into a padded (n_unique, multiplicity) table, then a sum over the last axis), instead of index_add_,
        # whose CUDA atomics add in a run-dependent order. With complex64 that order moved low band edges by up
        # to ~5e-4 between runs and broke exact replay of sessions (results/probe/NOTES.md).
        uniq, inv = np.unique(lin, return_inverse=True)
        counts = np.bincount(inv)
        order = np.argsort(inv, kind="stable")
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        pos = np.arange(len(lin)) - np.repeat(starts, counts)
        G = np.full((len(uniq), int(counts.max())), len(lin), dtype=np.int64)  # pad -> an appended zero
        G[inv[order], pos] = order
        self.uniq = torch.tensor(uniq, device=device)
        self.gather = torch.tensor(G, device=device)
        self.wrap = torch.tensor(mesh.wrap, device=device, dtype=rdt)  # (ne,8,3)
        self.N = N

    def __call__(self, ks: np.ndarray, nev: int = 12, chunk: int | None = None) -> np.ndarray:
        torch = self.torch
        N, ne = self.N, self.mesh.ne
        if chunk is None:  # keep three N x N complex matrices per k under ~6 GB
            per_k = 3 * N * N * (8 if self.dtype == torch.complex64 else 16)
            chunk = max(1, int(6e9 // per_k))
        out = []
        rdt = self.ke.dtype
        for s in range(0, len(ks), chunk):
            kk = torch.tensor(np.ascontiguousarray(ks[s:s + chunk]), device=self.dev, dtype=rdt)
            nk = kk.shape[0]
            ph = torch.exp(1j * torch.einsum("eid,kd->kei", self.wrap, kk).to(self.dtype))  # (nk,ne,8)
            ph = ph.repeat_interleave(3, dim=2)  # (nk,ne,24)
            P = ph.conj()[..., :, None] * ph[..., None, :]  # (nk,ne,24,24)
            K = torch.zeros((nk, N * N), device=self.dev, dtype=self.dtype)
            M = torch.zeros((nk, N * N), device=self.dev, dtype=self.dtype)
            zero = torch.zeros((nk, 1), device=self.dev, dtype=self.dtype)
            for T, e in ((K, self.ke), (M, self.me)):
                v = torch.cat([(P * e).reshape(nk, -1), zero], dim=1)
                T[:, self.uniq] = v[:, self.gather].sum(dim=-1)
                del v
            del P
            K = K.view(nk, N, N)
            M = M.view(nk, N, N)
            L = torch.linalg.cholesky(M)
            A = torch.linalg.solve_triangular(L, K, upper=False)
            A = torch.linalg.solve_triangular(L, A.mH, upper=False)  # L^-1 K L^-H (Hermitian)
            A = 0.5 * (A + A.mH)
            w = torch.linalg.eigvalsh(A)[:, :nev].real.double()
            out.append(w.cpu().numpy())
            del K, M, L, A
        w2 = np.concatenate(out)
        return np.sqrt(np.clip(w2, 0, None)) / (2 * np.pi * c_t(nu=self.nu))


def gaps(bands: np.ndarray, min_rel: float = 0.0) -> list[dict]:
    """Complete gaps between consecutive bands over the sampled k-points, widest relative gap first."""
    res = []
    for j in range(bands.shape[1] - 1):
        lo, hi = float(bands[:, j].max()), float(bands[:, j + 1].min())
        if hi > lo:
            rel = 2 * (hi - lo) / (hi + lo)
            if rel >= min_rel:
                res.append(dict(below_band=j + 1, f_lo=lo, f_hi=hi, rel=rel))
    return sorted(res, key=lambda g: -g["rel"])


# ---------------- certificate tier (CPU, inertia counts) -----------------
class InertiaCounter:
    """Counts Bloch eigenvalues below given frequencies, reusing the symbolic factorization across k and shifts."""

    def __init__(self, mesh: fem.CellMesh):
        self.mesh = mesh
        self.nu = mesh.nu
        self.solver = Pardiso(mtype=-2)

    def counts(self, k: np.ndarray, f_stars) -> list[dict]:
        m = self.mesh
        Kd = m.csr_data(m.element_values("K", k)).astype(complex)
        Md = m.csr_data(m.element_values("M", k)).astype(complex)
        out = []
        for f in f_stars:
            s = f_to_sigma(f, self.nu)
            A = m.real2n_upper(Kd - s * Md)
            st = self.solver.factor(A)
            out.append(dict(f=float(f), below=st["n_neg"] // 2, odd=st["n_neg"] % 2, perturbed=st["n_perturbed"]))
        return out

    def edge(self, k: np.ndarray, f: float, side: str, nev: int = 3) -> float | None:
        """Bloch frequency nearest to f on one side ("below": largest eigenvalue < f; "above": smallest > f).
        Shift-invert Lanczos on the complex Hermitian problem, with the inverse applied through the PARDISO
        factorization of the real 2N form at sigma(f) (the same matrix `counts` factors). Used to estimate gap edges
        for the discretization-convergence check; the rigorous part of the certificate stays the inertia counts."""
        from scipy.sparse.linalg import LinearOperator, eigsh

        checkpoint("certificate: gap-edge solve (Lanczos)")
        m = self.mesh
        N = m.ndof
        Kd = m.csr_data(m.element_values("K", k)).astype(complex)
        Md = m.csr_data(m.element_values("M", k)).astype(complex)
        K = sp.csr_matrix((Kd, m.indices, m.indptr), shape=(N, N))
        M = sp.csr_matrix((Md, m.indices, m.indptr), shape=(N, N))
        s = f_to_sigma(f, self.nu)
        self.solver.factor(m.real2n_upper(Kd - s * Md))

        def inv(x):
            x = np.asarray(x).ravel()
            y = self.solver.solve(np.concatenate([x.real, x.imag]))
            return y[:N] + 1j * y[N:]

        op = LinearOperator((N, N), matvec=inv, dtype=complex)
        # fixed start vector: ARPACK's default random start depends on the process's call history, which breaks
        # bit-exact replay of a session (amm.tools.replay); the converged values agree to the tolerance either way
        rng = np.random.default_rng(12345)
        v0 = rng.standard_normal(N) + 1j * rng.standard_normal(N)
        while True:  # widen until an eigenvalue on the requested side is found
            w = eigsh(K, k=nev, M=M, sigma=s, OPinv=op, which="LM", return_eigenvectors=False, tol=1e-7, v0=v0)
            fw = np.sqrt(np.clip(np.real(w), 0, None)) / (2 * np.pi * c_t(nu=self.nu))
            sel = fw[fw < f] if side == "below" else fw[fw > f]
            if len(sel) or nev >= 24:
                break
            nev *= 2
        if not len(sel):
            return None
        return float(sel.max() if side == "below" else sel.min())

    def free(self):
        self.solver.free()


def to_ibz(k: np.ndarray) -> np.ndarray:
    """Map wave vectors into the simple-cubic irreducible wedge pi >= kx >= ky >= kz >= 0 (cubic point group plus
    time reversal leave the Bloch spectrum of a cubic cell unchanged)."""
    k = np.mod(np.asarray(k, float) + np.pi, 2 * np.pi) - np.pi
    return np.ascontiguousarray(np.sort(np.abs(k), axis=-1)[..., ::-1])


_DIRS = np.array([d for d in np.ndindex(3, 3, 3) if d != (1, 1, 1)], float) - 1.0
_DIRS /= np.linalg.norm(_DIRS, axis=1, keepdims=True)


def adversarial_ks(mesh: fem.CellMesh, f_lo: float, f_hi: float, n_interior: int = 200, top: int = 3,
                   rounds: int = 6, seed: int = 11, device: str = "cuda", nev: int = 24) -> dict:
    """k-points where the bands bounding a claimed gap come closest to it, found with the GPU search tier on a
    coarse mesh: path plus `n_interior` random interior points, then a pattern search (26 directions, step halved
    each round) from the `top` best starts of each bounding band. The certificate adds them to its own k set, so
    an extremum inside the zone is not left to random sampling. Assumes cubic point symmetry of the cell."""
    gb = GPUBands(mesh, device=resolve_device(device))
    ks = np.vstack([kpath(8)[0], ibz_interior(n_interior, seed)])
    f = gb(ks, nev=nev)
    j = int((f[0] < f_lo).sum())  # bands below the claim at Gamma
    out = dict(below_band=j, ks=np.zeros((0, 3)))
    if not 0 < j < f.shape[1]:
        return out
    best = []
    for band, sgn in ((j - 1, -1.0), (j, 1.0)):  # maximize band j-1 (sgn -1 sorts descending); minimize band j
        order = np.argsort(sgn * f[:, band])[:top]
        cur, val = ks[order].copy(), f[order, band].copy()
        step = 0.15 * np.pi
        for rd in range(rounds):
            checkpoint("certificate: adversarial k search (GPU)", round=rd + 1, rounds=rounds)
            trial = to_ibz((cur[:, None, :] + step * _DIRS[None]).reshape(-1, 3))
            ft = gb(trial, nev=nev)[:, band].reshape(len(cur), -1)
            pick = np.argmin(sgn * ft, axis=1)
            better = sgn * ft[np.arange(len(cur)), pick] < sgn * val
            cur[better] = trial.reshape(len(cur), -1, 3)[better, pick[better]]
            val[better] = ft[better, pick[better]]
            step /= 2
        best.append((cur, val))
    out.update(ks=np.vstack([b[0] for b in best]),
               search_edges=[float(max(f[:, j - 1].max(), best[0][1].max())), float(min(f[:, j].min(), best[1][1].min()))])
    return out


def _extreme_edge(ic: InertiaCounter, ks: np.ndarray, f: float, side: str, below_band: int, start) -> tuple:
    """Gap edge over all sampled k: max over k of the eigenvalue just below f ("below") or min of the one just
    above f ("above"). Lanczos runs only at the `start` k-points; every other k is screened with one inertia count
    at the current edge (+/- 1e-6 relative). A k whose count shows a more extreme eigenvalue gets its own Lanczos
    solve and moves the edge. Already screened k stay valid because the edge only moves outward from f."""
    vals = {}
    for i in start:
        v = ic.edge(ks[i], f, side)
        if v is not None:
            vals[int(i)] = v
    pick = max if side == "below" else min
    e = pick(vals.values()) if vals else (0.0 if side == "below" else np.inf)
    for i in range(len(ks)):
        if i in vals or not np.isfinite(e):
            continue
        checkpoint("certificate: gap-edge screening", k=i + 1, n_k=len(ks))
        probe = e * (1 + 1e-6) if side == "below" else e * (1 - 1e-6)
        c = ic.counts(ks[i], [probe])[0]["below"]
        if (side == "below" and c < below_band) or (side == "above" and c > below_band):
            v = ic.edge(ks[i], f, side)
            if v is not None:
                vals[i] = v
                e = pick(e, v)
    arg = [i for i, v in vals.items() if v == e]
    return e, (arg[0] if arg else None), len(vals), vals


CONVERGENCE_SAFETY = 2.0  # calibrated on Lucklum & Vellekoop (2018): see results/verification/NOTES.md
P_MAX = 2.0  # largest convergence order the three-resolution guard will use (a fitted p above it is capped)
P_MIN = 0.25  # smallest order it will fit; slower convergence than this fails closed


def _order(h, f):
    """Fitted order p of f = f0 + C h^p through three points (h1 > h2 > h3), or None if the sequence is not
    monotone or no p in [P_MIN, 8] fits. The test is on the order equation in h, not on the raw steps: on a ladder
    with equal h-increments (e.g. n = 30, 40, 60) any p <= 1 gives steps that do not shrink, and a raw-step test
    excluded those admissible orders (confirm audit 2026-11-10; on 20/30/40 and 32/48/64 the raw-step test was
    implied by p > 0 and changed nothing)."""
    from scipy.optimize import brentq
    d12, d23 = f[1] - f[0], f[2] - f[1]
    if d12 == 0 or d23 == 0 or d12 * d23 < 0:
        return None
    g = lambda p: (h[1] ** p - h[2] ** p) / (h[0] ** p - h[1] ** p) - d23 / d12
    try:
        return brentq(g, P_MIN, 8.0)
    except ValueError:
        return None


def _edge_guard(ns, f, ph, safety, side):
    """Safe value of one gap edge. ns: three resolutions, f: edge values, ph: the edge at other grid phases of
    one resolution (with phase 0 included). Returns (safe, info); safe is None when the edge cannot be bounded.
    "lo" (top of the band below the gap): the safe value is above every estimate of the limit; "hi": below.
    A sequence that drifts monotonically toward the claim (lower edge rising, upper edge falling) must pass the
    order fit: when it does not (no order in [P_MIN, 8] fits the sequence) it is never read as phase noise,
    and the edge has no safe value (audit round 3, 2026-11-09; before, such a drift within twice the phase spread was
    bounded by the spread alone). A drift away from the claim is bounded by the computed values themselves."""
    h = [1 / n for n in ns]
    d12, d23 = f[1] - f[0], f[2] - f[1]
    P = max(ph) - min(ph) if ph else 0.0
    noise = P > 0 and abs(d12) <= safety * P and abs(d23) <= safety * P
    toward = d12 * d23 > 0 and (d23 > 0 if side == "lo" else d23 < 0)
    p = _order(h, f)
    if p is not None:
        pu = min(p, P_MAX)
        r = h[2] ** pu / (h[1] ** pu - h[2] ** pu)
        ext, err = f[2] + d23 * r, abs(d23) * r
    elif noise and not toward:
        ext, err = f[2], P
    elif noise:
        return None, dict(p=None, phase_spread=P, drift_toward_claim=True,
                          reason="monotone drift toward the claim without an admissible convergence order")
    else:
        return None, dict(p=None, phase_spread=P, reason="edge sequence neither convergent nor within phase noise")
    sgn = 1 if side == "lo" else -1
    # phase values enter as candidates (any discretization that puts the edge further into the claim bounds it);
    # an extra phase term anchored at the coarse phase values double-counted the noise (cube_bars c 0.6, w 0.2
    # refused although true; results/g2/NOTES.md)
    cands = list(f) + list(ph) + [ext + sgn * safety * err]
    safe = max(cands) if side == "lo" else min(cands)
    return safe, dict(p=p, p_used=min(p, P_MAX) if p else None, extrapolated=ext, remaining=err, phase_spread=P,
                      noise=bool(noise), drift_toward_claim=bool(toward))


def gap_convergence(edges: dict, f_lo: float, f_hi: float, safety: float = CONVERGENCE_SAFETY,
                    phase_edges: list | None = None) -> dict:
    """Discretization guard for a gap claim. edges: {n: (lo_n, hi_n)} = max band-j / min band-(j+1) over the
    sampled k. phase_edges: [(lo, hi), ...] at the grid phases of one resolution (cell shifted by a fraction of a
    voxel; the spread is pure discretization error, results/g2/NOTES.md).

    Two resolutions (n1 < n2): first-order assumption, f0 = f2 + (f2 - f1) h2 / (h1 - h2); the safe interval is
    the intersection of the per-resolution edges and the extrapolated edges moved inward by safety * |f2 - f1|.
    This cannot detect convergence slower than O(h).
    Three or more (the three finest are used): the order p is fitted per edge (capped at P_MAX; slower than
    P_MIN, or non-monotone beyond the phase noise, fails closed), the remaining error |d23| h3^p / (h2^p - h3^p)
    is moved inward by `safety`; edges at other grid phases (cut-voxel noise) are candidates of the bound, and when
    the sequence is not regular but within the phase noise the phase spread is the error, unless it drifts
    monotonically toward the claim (then the edge fails closed, `_edge_guard`). The claim must lie inside the safe
    interval."""
    ph_lo = [e[0] for e in phase_edges] if phase_edges else []
    ph_hi = [e[1] for e in phase_edges] if phase_edges else []
    if len(edges) >= 3:
        items = sorted(edges.items())[-3:]
        ns = [n for n, _ in items]
        lo_safe, lo_info = _edge_guard(ns, [e[0] for _, e in items], ph_lo, safety, "lo")
        hi_safe, hi_info = _edge_guard(ns, [e[1] for _, e in items], ph_hi, safety, "hi")
        ok = lo_safe is not None and hi_safe is not None and lo_safe < hi_safe and f_lo >= lo_safe and f_hi <= hi_safe
        return dict(edges={int(n): [lo, hi] for n, (lo, hi) in edges.items()}, mode="three-resolution",
                    lower_edge=lo_info, upper_edge=hi_info, phase_edges=phase_edges,
                    safe_interval=[lo_safe, hi_safe], safety=safety, passed=bool(ok))
    (n1, (lo1, hi1)), (n2, (lo2, hi2)) = sorted(edges.items())[-2:]
    r = (1 / n2) / (1 / n1 - 1 / n2)
    lo_ext, hi_ext = lo2 + (lo2 - lo1) * r, hi2 + (hi2 - hi1) * r
    lo_safe = max(lo1, lo2, lo_ext + safety * abs(lo2 - lo1), *ph_lo,
                  *([max(ph_lo) + safety * (max(ph_lo) - min(ph_lo))] if ph_lo else []))
    hi_safe = min(hi1, hi2, hi_ext - safety * abs(hi2 - hi1), *ph_hi,
                  *([min(ph_hi) - safety * (max(ph_hi) - min(ph_hi))] if ph_hi else []))
    return dict(edges={int(n): [lo, hi] for n, (lo, hi) in edges.items()}, mode="two-resolution O(h)",
                extrapolated=[lo_ext, hi_ext], phase_edges=phase_edges,
                safe_interval=[lo_safe, hi_safe], safety=safety,
                passed=bool(lo_safe < hi_safe and f_lo >= lo_safe and f_hi <= hi_safe))


def _edges_at(mesh, ks, idx_lo, idx_hi, f_lo, f_hi):
    """Edges on another mesh, by Lanczos at the given k indices only (no screening)."""
    ic = InertiaCounter(mesh if isinstance(mesh, fem.CellMesh) else fem.build_mesh(mesh))
    try:
        lo = [v for v in (ic.edge(ks[i], f_lo, "below") for i in idx_lo) if v is not None]
        hi = [v for v in (ic.edge(ks[i], f_hi, "above") for i in idx_hi) if v is not None]
    finally:  # the PARDISO factorization is freed on any exception or cancel too (G6, B9)
        ic.free()
    return (max(lo) if lo else None), (min(hi) if hi else None)


def certify_gap(meshes: dict, f_lo: float, f_hi: float, below_band: int | None = None, n_path: int = 4,
                n_interior: int = 10, seed: int = 0, zero_tol_f: float = 1e-3, convergence: bool = True,
                extra_ks: np.ndarray | None = None, edge_meshes: dict | None = None,
                phase_meshes: list | None = None) -> dict:
    """Certify that no Bloch eigenvalue lies in [f_lo, f_hi], for each resolution.

    meshes: {n: CellMesh} (or {n: mask/coverage array}, meshed without finite-cell sub-samples). If below_band is None it is read from the count at Gamma on the first resolution.
    Checks at every resolution:
      * Gamma: exactly 3 eigenvalues below zero_tol_f (rigid translations only; a non-percolating cell fails);
      * every sampled k (path + random interior + `extra_ks`, e.g. from `adversarial_ks`):
        count(f_lo) == count(f_hi) == below_band;
      * no perturbed pivots, and even raw counts (2N form sanity).
    With convergence=True and two or more resolutions, the gap edges are also estimated on the path at every
    resolution and the claim must lie inside the extrapolated safe interval (`gap_convergence`): edges that drift
    with resolution (e.g. thin-beam resonances converging from above) can otherwise pass both resolutions while
    being false in the converged limit.
    edge_meshes {n: mesh}: finer resolutions where only the edges are computed (Lanczos at the two most extreme
    k of the finest counted resolution, no counts), giving the third resolution of the order-fitted guard.
    phase_meshes: the finest counted resolution re-voxelized at other grid phases; edges at the same k give the
    phase-spread term. Both are used only when every counted resolution passes.
    """
    if not f_hi > f_lo > zero_tol_f:
        raise ValueError("need f_hi > f_lo > zero_tol_f")
    ks_path, _ = kpath(n_path)
    ks = np.vstack([ks_path, ibz_interior(n_interior, seed)] + ([np.asarray(extra_ks)] if extra_ks is not None
                                                                and len(extra_ks) else []))
    report = dict(claim=dict(below_band=below_band, f_lo=f_lo, f_hi=f_hi), n_k=len(ks), resolutions={}, passed=True)
    edges, edge_info, start_lo, start_hi, top = {}, {}, None, None, None
    for n, mesh in sorted(meshes.items()):
        t0 = time.perf_counter()
        mesh = mesh if isinstance(mesh, fem.CellMesh) else fem.build_mesh(mesh)
        ic = InertiaCounter(mesh)
        try:
            g, g_lo = ic.counts(np.zeros(3), [zero_tol_f, f_lo])
            if below_band is None:
                below_band = g_lo["below"]
                report["claim"]["below_band"] = below_band
            fails = []
            if g["below"] != 3:
                fails.append(dict(k="Gamma", reason=f"{g['below']} modes below f*={zero_tol_f} (expected 3)"))
            sane = g["perturbed"] == 0 and g["odd"] == 0
            for i, k in enumerate(ks):
                checkpoint("certificate: Bloch inertia counts", n=int(n), k=i + 1, n_k=len(ks))
                c_lo, c_hi = ic.counts(k, [f_lo, f_hi])
                sane &= c_lo["perturbed"] == 0 and c_hi["perturbed"] == 0 and c_lo["odd"] == 0 and c_hi["odd"] == 0
                if not (c_lo["below"] == below_band and c_hi["below"] == below_band):
                    fails.append(dict(k=np.round(k / np.pi, 4).tolist(), below_lo=c_lo["below"], below_hi=c_hi["below"]))
            if convergence and len(meshes) >= 2 and sane and not fails:  # edges only where the counts hold
                t1 = time.perf_counter()
                sym = list(dict((lab, i) for i, lab in reversed(kpath(n_path)[1])).values())  # first G, X, M, R
                lo_e, lo_arg, lo_n, lo_v = _extreme_edge(ic, ks, f_lo, "below", below_band, start_lo or sym)
                hi_e, hi_arg, hi_n, hi_v = _extreme_edge(ic, ks, f_hi, "above", below_band, start_hi or sym)
                top = (sorted(lo_v, key=lo_v.get, reverse=True)[:2], sorted(hi_v, key=hi_v.get)[:2])
                start_lo, start_hi = [lo_arg] if lo_arg is not None else None, [hi_arg] if hi_arg is not None else None
                edges[int(n)] = (lo_e, hi_e)
                edge_info[int(n)] = dict(k_lo=np.round(ks[lo_arg] / np.pi, 4).tolist() if lo_arg is not None else None,
                                         k_hi=np.round(ks[hi_arg] / np.pi, 4).tolist() if hi_arg is not None else None,
                                         lanczos_solves=lo_n + hi_n, seconds=round(time.perf_counter() - t1, 1))
        finally:  # freed on any exception or cancel too (G6, B9; was after the loop, outside a finally)
            ic.free()
        ok = sane and not fails
        report["resolutions"][int(n)] = dict(ndof=mesh.ndof, passed=bool(ok), numerically_sane=bool(sane),
                                             failures=fails[:10], n_failures=len(fails),
                                             seconds=round(time.perf_counter() - t0, 2))
        report["passed"] &= bool(ok)
    phase_edges = None
    if len(edges) == len(meshes) >= 2 and report["passed"] and top:
        t2 = time.perf_counter()
        for n, mesh in sorted((edge_meshes or {}).items()):
            e = _edges_at(mesh, ks, *top, f_lo, f_hi)
            if None in e:
                report["passed"] = False
                report["edge_failure"] = f"no edge found at n={n}"
                return report
            edges[int(n)] = e
        if phase_meshes:
            phase_edges = [edges[max(meshes)]] + [_edges_at(m, ks, *top, f_lo, f_hi) for m in phase_meshes]
            if any(None in e for e in phase_edges):
                report["passed"] = False
                report["edge_failure"] = "no edge found at a grid phase"
                return report
        report["edge_extra_seconds"] = round(time.perf_counter() - t2, 1)
        report["edge_k_kept"] = dict(lo=[np.round(ks[i] / np.pi, 4).tolist() for i in top[0]],
                                     hi=[np.round(ks[i] / np.pi, 4).tolist() for i in top[1]])
    if len(edges) >= 2:
        report["convergence"] = gap_convergence(edges, f_lo, f_hi, phase_edges=phase_edges)
        report["convergence"]["edge_search"] = edge_info
        report["passed"] &= report["convergence"]["passed"]
    return report
