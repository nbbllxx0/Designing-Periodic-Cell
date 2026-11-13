"""Parametric unit-cell families on a cell-centred voxel grid of the unit cube.

All families are cubic-symmetric. Parameters are fractions of the cell edge a.

F1 `tpms`      gyroid | schwarz_p | diamond | iwp, mode network|sheet, threshold t or target density
F2 `struts`    sc | bcc | octet, strut radius r, optional node-sphere radius R
F3 `resonator` cube_bars (core cube edge c, square bars of width w) |
               sphere_ligaments (core sphere radius c, round bars of diameter w)

Each family is a continuous field phi (solid where phi <= threshold). `make` returns partial-volume voxels: each
voxel's solid coverage from s^3 sub-samples. Binary voxels round thin and grid-aligned features to whole voxel
layers, so two certification resolutions describe different designs (first certificate run: rho 0.284 at n = 32
vs 0.253 at n = 48 for the cube-and-bars cell). Density matching by thresholding cannot fix grid-aligned faces
(ties), which is why coverage is used.

`clean(mask)` keeps the largest periodically face-connected component (edge- or corner-only contacts do not
count) and reports what was removed and whether the result percolates in x, y and z.
"""
from __future__ import annotations

import itertools

import numpy as np
from scipy import ndimage

TPMS = ("gyroid", "schwarz_p", "diamond", "iwp")
STRUTS = ("sc", "bcc", "octet")
RESONATORS = ("cube_bars", "sphere_ligaments")
FAMILIES = {"tpms": TPMS, "struts": STRUTS, "resonator": RESONATORS}
N_REF = 96


def grid(n: int, shift: float = 0.0):
    """Cell-centred sampling grid of the unit cube, translated by `shift` (cell units) along x, y and z.
    The shift is an explicit argument (B3, 2026-11-07); it used to be the module global _SHIFT set inside
    design_cell, which was not safe when two sessions voxelize at once. Same arithmetic: shift = 0.0 adds 0.0."""
    c = ((np.arange(n) + 0.5) / n + shift) % 1.0
    return np.meshgrid(c, c, c, indexing="ij")


# ---------------- fields -----------------
def tpms_field(kind: str, n: int, shift: float = 0.0) -> np.ndarray:
    X, Y, Z = (2 * np.pi * g for g in grid(n, shift))
    if kind == "gyroid":
        return np.sin(X) * np.cos(Y) + np.sin(Y) * np.cos(Z) + np.sin(Z) * np.cos(X)
    if kind == "schwarz_p":
        return np.cos(X) + np.cos(Y) + np.cos(Z)
    if kind == "diamond":
        return (np.sin(X) * np.sin(Y) * np.sin(Z) + np.sin(X) * np.cos(Y) * np.cos(Z)
                + np.cos(X) * np.sin(Y) * np.cos(Z) + np.cos(X) * np.cos(Y) * np.sin(Z))
    if kind == "iwp":
        return (2 * (np.cos(X) * np.cos(Y) + np.cos(Y) * np.cos(Z) + np.cos(Z) * np.cos(X))
                - (np.cos(2 * X) + np.cos(2 * Y) + np.cos(2 * Z)))
    raise ValueError(kind)


def _segments(kind: str) -> np.ndarray:
    """Strut segments (S,2,3) in cell coordinates, including the periodic images that touch the cell."""
    if kind == "sc":  # three bars through the cell centre
        segs = [((0, .5, .5), (1, .5, .5)), ((.5, 0, .5), (.5, 1, .5)), ((.5, .5, 0), (.5, .5, 1))]
    elif kind == "bcc":  # body diagonals through the centre
        segs = [((0, 0, 0), (1, 1, 1)), ((1, 0, 0), (0, 1, 1)), ((0, 1, 0), (1, 0, 1)), ((0, 0, 1), (1, 1, 0))]
    elif kind == "octet":  # FCC nearest-neighbour bonds: corners + face centres, length 1/sqrt(2)
        pts = [np.array(p, float) for p in itertools.product((0, 1), repeat=3)]
        for d in range(3):
            for s in (0, 1):
                p = np.full(3, 0.5)
                p[d] = s
                pts.append(p)
        pts = np.array(pts)
        L = 1 / np.sqrt(2)
        segs = [(tuple(pts[i]), tuple(pts[j])) for i in range(len(pts)) for j in range(i + 1, len(pts))
                if abs(np.linalg.norm(pts[i] - pts[j]) - L) < 1e-9]
    else:
        raise ValueError(kind)
    return np.array(segs, float)


def _nodes(kind: str) -> np.ndarray:
    if kind == "sc":
        return np.array([[.5, .5, .5]])
    if kind == "bcc":
        return np.array([[.5, .5, .5]] + [list(p) for p in itertools.product((0, 1), repeat=3)], float)
    if kind == "octet":
        return np.unique(_segments("octet").reshape(-1, 3), axis=0)
    raise ValueError(kind)


def _dist_to_segments(P: np.ndarray, segs: np.ndarray) -> np.ndarray:
    d2 = np.full(len(P), np.inf)
    for a, b in segs:
        ab = b - a
        t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
        q = P - a - t[:, None] * ab
        d2 = np.minimum(d2, np.einsum("ij,ij->i", q, q))
    return np.sqrt(d2)


def _box(X, Y, Z, hx, hy, hz):
    return np.maximum(np.maximum(np.abs(X) - hx, np.abs(Y) - hy), np.abs(Z) - hz)


def field(family: str, kind: str, n: int, *, shift: float = 0.0, **p) -> tuple[np.ndarray, float | None]:
    """Field phi on the n^3 grid (translated by `shift` cell units) and its natural threshold (None: only a target
    density defines the solid)."""
    if family == "tpms":
        f = tpms_field(kind, n, shift)
        phi = np.abs(f) if p.get("mode", "network") == "sheet" else f
        return phi, (None if p.get("density") is not None else p.get("t"))
    if family == "struts":
        P = np.stack([g.ravel() for g in grid(n, shift)], axis=1)
        phi = _dist_to_segments(P, _segments(kind)) - p["r"]
        if p.get("R", 0) > 0:
            dn = np.min(np.linalg.norm(P[:, None, :] - _nodes(kind)[None], axis=2), axis=1) - p["R"]
            phi = np.minimum(phi, dn)
        return phi.reshape(n, n, n), 0.0
    if family == "resonator":
        c, w = p["c"], p["w"]
        X, Y, Z = (g - 0.5 for g in grid(n, shift))
        if kind == "cube_bars":
            core = _box(X, Y, Z, c / 2, c / 2, c / 2)
            bars = np.minimum(np.minimum(_box(X, Y, Z, 1, w / 2, w / 2), _box(X, Y, Z, w / 2, 1, w / 2)),
                              _box(X, Y, Z, w / 2, w / 2, 1))
        elif kind == "sphere_ligaments":
            core = np.sqrt(X**2 + Y**2 + Z**2) - c
            bars = np.minimum(np.minimum(np.sqrt(Y**2 + Z**2), np.sqrt(X**2 + Z**2)), np.sqrt(X**2 + Y**2)) - w / 2
        else:
            raise ValueError(kind)
        return np.minimum(core, bars), 0.0
    raise ValueError(family)


N_FINE = 96  # supersampling: each voxel gets s^3 samples with n*s >= N_FINE
C_MIN = 0.01  # voxels with less solid coverage are void (near-empty elements make K - sM near-singular)


def supersample(n: int) -> int:
    return max(2, int(np.ceil(N_FINE / n)))


def _signed_distance(phi: np.ndarray, thr: float, h: float) -> np.ndarray:
    """Approximate signed distance (negative inside) from a level-set field: (phi - thr) / |grad phi|."""
    q = np.pad(phi, 1, mode="wrap")
    g = np.gradient(q, h)
    gm = np.sqrt(sum(gi**2 for gi in g))[1:-1, 1:-1, 1:-1]
    return (phi - thr) / np.maximum(gm, 1e-6)


def _soft(dist: np.ndarray, delta: float) -> np.ndarray:
    """Solid fraction of a sub-sample of width delta whose centre lies at signed distance dist (exact for planes)."""
    return np.clip(0.5 - dist / delta, 0.0, 1.0)


def _fine_coverage(family: str, kind: str, n: int, offset_voxels: float = 0.0, nf: int | None = None,
                   shift: float = 0.0, **p) -> tuple[np.ndarray, int]:
    """Anti-aliased sub-sample solid fractions on an nf^3 grid (nf a multiple of n), sampling grid translated by
    `shift` cell units; returns (sub, nf // n)."""
    nf = nf or n * supersample(n)
    assert nf % n == 0
    s = nf // n
    delta = 1.0 / nf
    phi, thr = field(family, kind, nf, shift=shift, **p)
    if thr is None:  # density-defined TPMS: find the threshold whose soft volume equals the target density
        target = p["density"]
        flat = np.sort(phi.ravel())
        lo_t = flat[0] - 1.0
        hi_t = flat[-1] + 1.0
        t = flat[min(max(int(round(target * flat.size)), 1), flat.size - 1)]
        for _ in range(40):
            v = _soft(_signed_distance(phi, t, delta), delta).mean()
            if abs(v - target) < 1e-6:
                break
            lo_t, hi_t = (t, hi_t) if v < target else (lo_t, t)
            t = 0.5 * (lo_t + hi_t)
        thr = t
    dist = _signed_distance(phi, thr, delta) - offset_voxels / n
    return _soft(dist, delta), s


def make(family: str, kind: str, n: int, coverage: bool = True, offset_voxels: float = 0.0, **p) -> np.ndarray:
    """Voxelize a design at resolution n.

    coverage=True (default): float array of solid volume fraction per voxel from s^3 anti-aliased sub-samples
    (partial-volume voxels; stiffness and mass scale with it). Densities agree across resolutions.
    offset_voxels: +k dilates / -k erodes the surface by k voxel widths (as-built perturbation), applied as a
    shift of the signed distance, so it is resolution-consistent.
    coverage=False: binary mask at voxel centres (legacy; resolution-inconsistent for thin features).
    """
    if not coverage:
        phi, thr = field(family, kind, n, **p)
        if thr is None:
            flat = np.sort(phi.ravel())
            thr = flat[min(max(int(round(p["density"] * flat.size)), 1), flat.size - 1)]
        return phi <= thr
    return voxelize(family, kind, n, offset_voxels=offset_voxels, **p)[0]


def voxelize(family: str, kind: str, n: int, offset_voxels: float = 0.0, **p) -> tuple[np.ndarray, np.ndarray]:
    """Coverage (n,n,n) and sub-sample solid fractions (n,s,n,s,n,s) for finite-cell integration."""
    sub, s = _fine_coverage(family, kind, n, offset_voxels=offset_voxels, **p)
    sub6 = sub.reshape(n, s, n, s, n, s)
    cov = sub6.mean(axis=(1, 3, 5))
    drop = cov < C_MIN
    cov[drop] = 0.0
    sub6 = sub6 * (~drop)[:, None, :, None, :, None]
    return cov, sub6


def _finish(sub: np.ndarray, n: int):
    s = sub.shape[0] // n
    sub6 = sub.reshape(n, s, n, s, n, s)
    cov = sub6.mean(axis=(1, 3, 5))
    drop = cov < C_MIN
    cov[drop] = 0.0
    cov_c, info = clean(cov)
    return cov_c, sub6 * (cov_c > 0)[:, None, :, None, :, None], info


def design_cell(spec: dict, n: int, offset_voxels: float = 0.0, phase: float = 0.0):
    """Voxelize and clean a design spec {"family","kind","params"}: (coverage, sub6, info).
    phase: translate the design by this many voxel widths along x, y and z before voxelizing. The cell is
    periodic, so the physics is unchanged; differences between phases measure the discretization error from where
    the surfaces cut the voxels (certify.static_block uses this). The phase is passed down explicitly as
    shift = phase / n (no module state)."""
    sub, _ = _fine_coverage(spec["family"], spec["kind"], n, offset_voxels=offset_voxels, shift=phase / n,
                            **spec["params"])
    return _finish(sub, n)


def design_cells(spec: dict, ns: tuple, nf: int) -> dict:
    """Several resolutions from ONE fine sub-sample grid (nf divisible by every n): {n: (coverage, sub6, info)}.
    Used by the search tier, where the field evaluation dominates the cost."""
    sub, _ = _fine_coverage(spec["family"], spec["kind"], max(ns), nf=nf, **spec["params"])
    return {n: _finish(sub, n) for n in ns}


def tpms(kind: str, n: int, t: float | None = None, mode: str = "network", density: float | None = None, **kw):
    return make("tpms", kind, n, t=t, mode=mode, density=density, **kw)


def struts(kind: str, n: int, r: float, R: float = 0.0, **kw):
    return make("struts", kind, n, r=r, R=R, **kw)


def resonator(kind: str, n: int, c: float, w: float, **kw):
    return make("resonator", kind, n, c=c, w=w, **kw)


# ---------------- connectivity -----------------
def periodic_labels(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Face-connectivity labels with periodic identification of opposite faces."""
    lab, nl = ndimage.label(np.asarray(mask) > 0)  # 6-connectivity
    parent = np.arange(nl + 1)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for d in range(3):
        a = np.take(lab, 0, axis=d)
        b = np.take(lab, -1, axis=d)
        both = (a > 0) & (b > 0)
        for u, v in set(zip(a[both].tolist(), b[both].tolist())):
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[max(ru, rv)] = min(ru, rv)
    roots = np.array([find(i) for i in range(nl + 1)])
    _, inv = np.unique(roots, return_inverse=True)
    return inv[lab], int(inv.max())


def percolates(mask: np.ndarray) -> list[bool]:
    """Per direction: a face-connected path through three stacked copies touches both end faces."""
    out = []
    mask = np.asarray(mask) > 0
    for d in range(3):
        lab, _ = ndimage.label(np.concatenate([mask] * 3, axis=d))
        a = set(np.unique(np.take(lab, 0, axis=d)).tolist()) - {0}
        b = set(np.unique(np.take(lab, -1, axis=d)).tolist()) - {0}
        out.append(bool(a & b))
    return out


FEATURE_GRID = 128  # grid of the numeric feature estimate (TPMS); 1/128 of the cell edge per voxel


def _bottleneck(solid: np.ndarray) -> float:
    """Diameter (cell units) of the largest ball that passes through a periodic binary solid along each of x, y and
    z: the largest r whose set {distance to the void > r} still percolates in all three directions, by bisection
    over the distinct distance values. Distances are between voxel centres; half a voxel is added for the surface
    lying between the last solid and the first void centre."""
    n = solid.shape[0]
    pad = n // 4
    edt = ndimage.distance_transform_edt(np.pad(solid, pad, mode="wrap"))[(slice(pad, -pad),) * 3]
    vals = np.unique(edt[solid])
    if not len(vals) or not all(percolates(solid)):
        return 0.0
    lo, hi = 0, len(vals) - 1  # vals[lo] percolates (> vals[lo] - eps keeps the whole solid at lo = 0)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if all(percolates(edt >= vals[mid])):
            lo = mid
        else:
            hi = mid - 1
    return float(2 * (vals[lo] + 0.5) / n)


def thinnest_feature(spec: dict, n_grid: int = FEATURE_GRID) -> dict:
    """Load-path feature size of a design, in cell units: the diameter of the largest ball that can pass through the
    solid along x, y and z (the bottleneck of every load path; a thin spot that loads can route around does not set
    it). Exact from the parameters where the family defines it: resonators, the bar width w (square bar of
    `cube_bars`, round bar of `sphere_ligaments`); struts, the strut diameter 2r (node spheres only widen the
    joints). TPMS: computed by `_bottleneck` on an n_grid^3 binary grid (resolution 1/n_grid). The certificate uses
    it to require that the finest resolution of each block spans the feature by `certify.FEATURE_MIN_VOXELS`."""
    fam, p = spec["family"], spec["params"]
    if fam == "resonator":
        return dict(size=float(p["w"]), method="parameter w (bar width)")
    if fam == "struts":
        return dict(size=float(2 * p["r"]), method="parameter 2r (strut diameter)")
    sub, _ = _fine_coverage(fam, spec["kind"], n_grid, nf=n_grid, **p)
    return dict(size=_bottleneck(sub >= 0.5), method=f"load-path bottleneck on a {n_grid}^3 grid")


def clean(field: np.ndarray) -> tuple[np.ndarray, dict]:
    """Keep the largest periodic face-connected component of a mask or coverage field (by solid volume)."""
    field = np.asarray(field)
    w = field.astype(float)
    lab, ncomp = periodic_labels(field)
    if ncomp == 0:
        return field.copy(), dict(n_components=0, removed_voxels=0, removed_fraction=0.0, density=0.0,
                                  percolates=[False] * 3)
    vol = np.bincount(lab.ravel(), weights=w.ravel())
    vol[0] = 0
    keep = lab == int(np.argmax(vol))
    out = np.where(keep, field, 0).astype(field.dtype)
    removed = float(w.sum() - w[keep].sum())
    return out, dict(n_components=ncomp, removed_voxels=int((field > 0).sum() - keep.sum()),
                     removed_fraction=removed / max(w.sum(), 1e-300), density=float(np.where(keep, w, 0).mean()),
                     percolates=percolates(keep))
