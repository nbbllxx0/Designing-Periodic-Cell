"""Exported-geometry recheck (V6 step 6): re-voxelize an exported single-cell STL at an independent resolution and
recompute density, the static constants and the gap counts with amm's solvers on THAT geometry.

The STL is read here (binary STL reader written for V6; trimesh is not installed). Inside/outside is decided by ray
parity along +z for every sample point (x_i, y_j, z_k) of an (n s)^3 cell-centred grid, with the sample grid
jittered by a tiny irrational offset so that rays never hit a triangle edge or vertex exactly. The voxel coverage
is the mean of its s^3 samples, and the sub-samples feed amm's finite-cell elements exactly like
geometry.design_cell's: the geometry model is replaced, everything downstream is amm's (fem.build_mesh,
homog.homogenize, bloch.certify_gap). The coverage field is cleaned to its largest periodic face-connected
component (geometry.clean, as every certificate solve does).

Independence: the export contoured the level-set field at resolution 64 (marching cubes); the certificate sampled
the field itself at 96+ sub-samples per edge. Here only the triangle surface is used, at a different grid.
"""
from __future__ import annotations

import struct

import numpy as np

import amm  # noqa: F401
from amm import geometry

JITTER = (1.0 / np.e) * 1e-6, (1.0 / np.pi) * 1e-6, (np.sqrt(2) - 1) * 1e-6  # cell units


def read_stl(path) -> np.ndarray:
    """Binary STL -> triangles (T, 3, 3) float64."""
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[80:84])[0]
    rec = np.frombuffer(b, dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")], count=n, offset=84)
    return rec["v"].astype(np.float64)


def inside_points(t: np.ndarray, xs: np.ndarray, ys: np.ndarray, zs: np.ndarray) -> tuple[np.ndarray, int]:
    """Boolean (len xs, len ys, len zs): point (xs[i], ys[j], zs[k]) inside the closed triangle surface t (cell
    units), by ray parity along +z. xs and ys must be sorted ascending. Returns (inside, odd-parity columns)."""
    x0, y0 = t[:, :, 0], t[:, :, 1]
    lo_i = np.searchsorted(xs, x0.min(1), "left")
    hi_i = np.searchsorted(xs, x0.max(1), "right") - 1
    lo_j = np.searchsorted(ys, y0.min(1), "left")
    hi_j = np.searchsorted(ys, y0.max(1), "right") - 1
    ni, nj = hi_i - lo_i + 1, hi_j - lo_j + 1
    idx = np.flatnonzero((ni > 0) & (nj > 0))
    cnt = ni[idx] * nj[idx]
    tri_id = np.repeat(idx, cnt)
    start = np.repeat(np.cumsum(cnt) - cnt, cnt)
    loc = np.arange(len(tri_id)) - start
    ii = lo_i[tri_id] + loc % ni[tri_id]
    jj = lo_j[tri_id] + loc // ni[tri_id]
    px, py = xs[ii], ys[jj]
    A, B, C = t[tri_id, 0], t[tri_id, 1], t[tri_id, 2]
    d = (B[:, 1] - C[:, 1]) * (A[:, 0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (A[:, 1] - C[:, 1])
    with np.errstate(divide="ignore", invalid="ignore"):
        l1 = ((B[:, 1] - C[:, 1]) * (px - C[:, 0]) + (C[:, 0] - B[:, 0]) * (py - C[:, 1])) / d
        l2 = ((C[:, 1] - A[:, 1]) * (px - C[:, 0]) + (A[:, 0] - C[:, 0]) * (py - C[:, 1])) / d
        l3 = 1 - l1 - l2
        hit = (d != 0) & (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        z = l1 * A[:, 2] + l2 * B[:, 2] + l3 * C[:, 2]
    nx = len(xs)
    col = (ii + nx * jj)[hit]
    z = z[hit]
    order = np.lexsort((z, col))
    col, z = col[order], z[order]
    inside = np.zeros((len(xs), len(ys), len(zs)), bool)
    bounds = np.searchsorted(col, np.arange(nx * len(ys) + 1))
    odd = 0
    for c in np.flatnonzero(np.diff(bounds)):
        zc = z[bounds[c]:bounds[c + 1]]
        odd += len(zc) % 2
        inside[c % nx, c // nx, :] = (np.searchsorted(zc, zs) % 2) == 1
    return inside, odd


def sample_grid(N: int, shift: float = 0.0):
    """amm.geometry.grid convention: sample i at ((i + 0.5) / N + shift) mod 1, plus the tiny jitter per axis.
    Returns per axis (sorted positions, permutation back to sample order)."""
    out = []
    for j in JITTER:
        pos = ((np.arange(N) + 0.5) / N + shift) % 1.0 + j
        order = np.argsort(pos)
        out.append((pos[order], np.argsort(order)))
    return out


def inside_grid(tri: np.ndarray, N: int, a: float, shift: float = 0.0) -> tuple[np.ndarray, int]:
    """Boolean (N,N,N) on the amm sample grid (translated by `shift` cell units), STL vertices in units of a."""
    (xs, ix), (ys, iy), (zs, iz) = sample_grid(N, shift)
    ins, odd = inside_points(tri / a, xs, ys, zs)
    return ins[ix][:, iy][:, :, iz], odd


def voxelize_stl(path, n: int, s: int, a_mm: float, phase: float = 0.0):
    """(coverage (n,n,n), sub6 (n,s,n,s,n,s), clean info, raw stats) of the STL cell at n voxels, s^3 samples each."""
    tri = read_stl(path)
    ins, odd = inside_grid(tri, n * s, a_mm, shift=phase / n)
    ins = ins.astype(float)
    sub6 = ins.reshape(n, s, n, s, n, s)
    cov = sub6.mean(axis=(1, 3, 5))
    drop = cov < geometry.C_MIN
    cov[drop] = 0.0
    raw_density = float(ins.mean())
    cov_c, info = geometry.clean(cov)
    sub6 = sub6 * (cov_c > 0)[:, None, :, None, :, None]
    return cov_c, sub6, info, dict(n_triangles=int(len(tri)), raw_sample_density=raw_density,
                                   odd_parity_columns=int(odd),
                                   samples_per_edge=n * s)


# ---------------------------------------------------------------------------------------------------------------
# anti-aliased coverage (deviation 3): exact inside length along rays in x, y and z through the fine-cell centres
# ---------------------------------------------------------------------------------------------------------------
def _ray_crossings(t, xs, ys):
    """Per (x, y) column: sorted z of the surface crossings (list of arrays, column index i + len(xs) j)."""
    x0, y0 = t[:, :, 0], t[:, :, 1]
    lo_i = np.searchsorted(xs, x0.min(1), "left"); hi_i = np.searchsorted(xs, x0.max(1), "right") - 1
    lo_j = np.searchsorted(ys, y0.min(1), "left"); hi_j = np.searchsorted(ys, y0.max(1), "right") - 1
    ni, nj = hi_i - lo_i + 1, hi_j - lo_j + 1
    idx = np.flatnonzero((ni > 0) & (nj > 0))
    cnt = ni[idx] * nj[idx]
    tri_id = np.repeat(idx, cnt)
    start = np.repeat(np.cumsum(cnt) - cnt, cnt)
    loc = np.arange(len(tri_id)) - start
    ii = lo_i[tri_id] + loc % ni[tri_id]
    jj = lo_j[tri_id] + loc // ni[tri_id]
    px, py = xs[ii], ys[jj]
    A, B, C = t[tri_id, 0], t[tri_id, 1], t[tri_id, 2]
    d = (B[:, 1] - C[:, 1]) * (A[:, 0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (A[:, 1] - C[:, 1])
    with np.errstate(divide="ignore", invalid="ignore"):
        l1 = ((B[:, 1] - C[:, 1]) * (px - C[:, 0]) + (C[:, 0] - B[:, 0]) * (py - C[:, 1])) / d
        l2 = ((C[:, 1] - A[:, 1]) * (px - C[:, 0]) + (A[:, 0] - C[:, 0]) * (py - C[:, 1])) / d
        l3 = 1 - l1 - l2
        hit = (d != 0) & (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        z = l1 * A[:, 2] + l2 * B[:, 2] + l3 * C[:, 2]
    col = (ii + len(xs) * jj)[hit]
    z = z[hit]
    order = np.lexsort((z, col))
    return col[order], z[order]


def _axis_coverage(t, centres, edges):
    """Fraction of each fine cell inside, from the exact inside length along +z rays through the (x, y) centres.
    centres: sorted sample positions (x and y); edges: sorted z cell edges (len N + 1). Returns (N, N, N), odd."""
    N = len(centres)
    col, z = _ray_crossings(t, centres, centres)
    bounds = np.searchsorted(col, np.arange(N * N + 1))
    cov = np.zeros((N, N, N))
    odd = 0
    for c in np.flatnonzero(np.diff(bounds)):
        zc = z[bounds[c]:bounds[c + 1]]
        if len(zc) % 2:
            odd += 1
            zc = zc[:-1]
        a, b = zc[0::2], zc[1::2]
        # inside length below each edge: F(e) = sum clip(e - a, 0, b - a)
        F = np.clip(edges[:, None] - a[None, :], 0.0, (b - a)[None, :]).sum(1)
        cov[c % N, c // N, :] = np.diff(F) / np.diff(edges)
    return cov, odd


def coverage_grid(tri: np.ndarray, N: int, a: float, shift: float = 0.0) -> tuple[np.ndarray, int]:
    """Anti-aliased solid fraction (N,N,N) of the fine cells of the amm sample grid translated by `shift`.
    Rays along x, y and z through the fine-cell centres each give the exact inside fraction along their axis; per
    fine cell, the directions that see a partial value (0 < f < 1) are averaged (a face normal to an axis is
    resolved exactly by that axis' ray); if none does, the cell is fully in or out (all agree up to aliasing at
    edges, where the majority is taken). The cell is periodic: positions wrap mod 1 into the closed cell STL, so
    a shifted grid is evaluated on the cell translated by -shift with its 27 periodic images clipped by the rays."""
    t = tri / a
    h = 1.0 / N
    base = (np.arange(N) + 0.5) * h
    edges = np.arange(N + 1) * h
    if shift:
        # translate the periodic solid by -shift: images in [-1, 1]^3 cover [0, 1)^3 after the shift
        imgs = [t - shift + np.array(o, float) for o in np.ndindex(2, 2, 2)]
        t = np.concatenate(imgs)
        # crossings outside [0, 1] from images are harmless: inside intervals are clipped by the cell edges, and
        # every image is closed at its own cell walls (the walls of neighbouring images coincide and cancel in
        # parity only if both are present, which the 8 images guarantee inside [0, 1]^3)
    covs, odd = [], 0
    for perm in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):     # ray axis = perm[2]
        tp = t[:, :, list(perm)]
        cv, o = _axis_coverage(tp + JITTER[0] * np.array([1, 0.7, 0.0]), base, edges)
        odd += o
        inv = np.argsort(perm)
        covs.append(np.transpose(cv, inv))
    S = np.stack(covs)                                    # (3, N, N, N)
    part = (S > 1e-9) & (S < 1 - 1e-9)
    npart = part.sum(0)
    avg_part = np.where(npart > 0, (S * part).sum(0) / np.maximum(npart, 1), 0.0)
    maj = (S.mean(0) > 0.5).astype(float)
    return np.where(npart > 0, avg_part, maj), odd


def voxelize_stl_aa(path, n: int, s: int, a_mm: float, phase: float = 0.0):
    """As voxelize_stl, with anti-aliased fine-cell fractions (coverage_grid)."""
    tri = read_stl(path)
    fine, odd = coverage_grid(tri, n * s, a_mm, shift=phase / n)
    sub6 = fine.reshape(n, s, n, s, n, s)
    cov = sub6.mean(axis=(1, 3, 5))
    cov[cov < geometry.C_MIN] = 0.0
    cov_c, info = geometry.clean(cov)
    sub6 = sub6 * (cov_c > 0)[:, None, :, None, :, None]
    return cov_c, sub6, info, dict(n_triangles=int(len(tri)), raw_sample_density=float(fine.mean()),
                                   odd_parity_columns=int(odd), samples_per_edge=n * s, method="anti-aliased rays x/y/z")
