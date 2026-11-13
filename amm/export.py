"""Geometry export (single-cell and tiled STL) and manufacturing screening (plan item B2).

Geometry. The exported solid is the design's level set as the certificate sees it: the anti-aliased solid fraction
of `geometry` sampled on an n^3 grid per cell (`resolution`), cleaned to its largest periodic face-connected
component (`geometry.clean`, as every certificate solve is), and contoured at solid fraction 0.5. With scikit-image
the surface is extracted by marching cubes (Lewiner); without it, the boundary faces of the voxels with solid
fraction >= 0.5 are written (a stair-stepped surface; `method` says which). The single cell is closed at the cell
walls; the tiled block is the periodic field repeated tiles^3 times and contoured once, so neighbouring cells merge
into one solid. Lengths are in mm when the cell size is known, else in cell units (a = 1).

Manufacturing screening (NOT a printability claim). Three checks, each with its stated assumptions:
  * minimum feature: morphological opening of the voxel solid (fraction >= 0.5) with a ball of diameter L removes
    every solid feature thinner than L. `solid_thinner_than_limit` is the fraction of the solid volume removed at
    the printer limit; the screen passes when it is <= FEATURE_TOL (1 %). The estimated minimum feature is the
    largest L on the voxel grid for which the removed fraction stays <= FEATURE_TOL. The same on the void phase
    gives the smallest channel or pore (powder removal), reported against the same limit. Resolution: one voxel
    (a / resolution); the periodic cell is wrapped, so features crossing the cell walls are measured whole.
  * tiled connectivity: the tiles^3 block (not periodic: a finite printed part) is one face-connected piece that
    spans the block in x, y and z.
  * watertight surface: every edge of the triangle mesh is shared by exactly two triangles with opposite
    orientation (closed, manifold, consistently oriented); the enclosed volume (divergence theorem) is reported
    against the voxel solid volume.
The printer limit is the material's typical minimum feature (amm.units.MATERIALS, a datasheet value for the
process) unless the caller states one. Passing the screen does not mean the part can be printed: support, powder
removal, residual stress, surface roughness and process parameters are not checked.
"""
from __future__ import annotations

import hashlib
import struct

import numpy as np
from scipy import ndimage

from . import geometry

EXPORT_SCHEMA = "amm-export/1"
SCREEN_SCHEMA = "amm-screen/1"
FEATURE_TOL = 0.01
SCREEN_DISCLAIMER = ("manufacturing screening only, NOT a printability claim: minimum feature against a stated "
                     "printer limit (one-voxel resolution), tiled connectivity and a watertight surface are checked; "
                     "support, powder removal, residual stress, roughness and process parameters are not")
REPORT_DISCLAIMERS = [
    SCREEN_DISCLAIMER,
    "certificates are acceptance under stated discretization, sampling and guard assumptions, not continuum "
    "theorems; a gap is certified for the infinite periodic lattice, not for a finite printed block",
    "search-tier values (evaluate, search, atlas) are estimates, biased stiff and high in frequency, NOT certificates",
    "material values are typical datasheet inputs of the request, not measured properties of a printed part",
    "the as-built check is a robustness flag (surface offset +-offset a), not a tolerance analysis",
]


# ---------------------------------------------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------------------------------------------
def solid_field(spec: dict, resolution: int) -> tuple[np.ndarray, dict]:
    """Cleaned solid fraction on a resolution^3 grid of one cell (one sample per voxel)."""
    sub, _ = geometry._fine_coverage(spec["family"], spec["kind"], resolution, nf=resolution, **spec["params"])
    cov = np.where(sub < geometry.C_MIN, 0.0, sub)
    cov_c, info = geometry.clean(cov)
    return cov_c.astype(np.float64), info


def _weld(V: np.ndarray, F: np.ndarray, decimals: int = 9) -> tuple[np.ndarray, np.ndarray]:
    key = np.round(V, decimals)
    U, inv = np.unique(key, axis=0, return_inverse=True)
    F = inv.reshape(-1)[F]
    keep = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    return U, F[keep]


def _voxel_faces(m: np.ndarray, h: float) -> tuple[np.ndarray, np.ndarray]:
    """Boundary faces of a binary voxel set (zero outside), outward-oriented, vertices welded."""
    pad = np.pad(m, 1)
    corner = {
        (0, 1): [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], (0, -1): [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
        (1, 1): [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)], (1, -1): [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
        (2, 1): [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], (2, -1): [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)],
    }
    core = pad[1:-1, 1:-1, 1:-1]
    verts, faces, base = [], [], 0
    for (ax, sg), cs in corner.items():
        sl = [slice(1, -1)] * 3
        sl[ax] = slice(1 + sg, pad.shape[ax] - 1 + sg)
        idx = np.argwhere(core & ~pad[tuple(sl)])
        if not len(idx):
            continue
        q = (idx[:, None, :] + np.array(cs)[None]).reshape(-1, 3).astype(float) * h
        k = np.arange(len(idx)) * 4 + base
        verts.append(q)
        faces.append(np.stack([np.stack([k, k + 1, k + 2], 1), np.stack([k, k + 2, k + 3], 1)], 1).reshape(-1, 3))
        base += len(q)
    if not verts:
        return np.zeros((0, 3)), np.zeros((0, 3), int)
    return _weld(np.concatenate(verts), np.concatenate(faces))


def surface(field: np.ndarray, h: float, method: str = "auto") -> tuple[np.ndarray, np.ndarray, str]:
    """Closed surface of {field >= 0.5} (field zero outside the array), vertices in the units of h, origin at the
    lower array corner. Returns (V, F, method)."""
    if method in ("auto", "marching_cubes"):
        try:
            from skimage.measure import marching_cubes
        except ImportError:
            if method == "marching_cubes":
                raise ImportError("marching-cubes export needs scikit-image: pip install amm[export]") from None
            method = "voxel_faces"
        else:
            pad = np.pad(field, 1)
            V, F, _, _ = marching_cubes(pad, level=0.5, spacing=(h, h, h), allow_degenerate=False,
                                        method="lewiner")
            V = V - 0.5 * h  # voxel i (padded i+1) has its centre at (i + 1/2) h
            # scikit-image winds the triangles so that the normals point up the field (into the solid): reverse
            # them for outward normals (mesh_check: positive enclosed volume)
            V, F = _weld(V.astype(np.float64), F[:, ::-1].astype(np.int64))
            return V, F, "marching_cubes"
    V, F = _voxel_faces(field >= 0.5, h)
    return V, F, "voxel_faces"


def mesh_check(V: np.ndarray, F: np.ndarray) -> dict:
    """Closed / manifold / oriented test, enclosed volume and number of shells (connected surface pieces)."""
    if len(F) == 0:
        return dict(n_triangles=0, watertight=False, boundary_edges=0, nonmanifold_edges=0, orientation_ok=False,
                    volume=0.0, n_shells=0)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    und = np.sort(e, axis=1)
    _, cnt = np.unique(und, axis=0, return_counts=True)
    _, dcnt = np.unique(e, axis=0, return_counts=True)
    boundary, nonman = int((cnt == 1).sum()), int((cnt > 2).sum())
    orient = bool((dcnt == 1).all())
    tri = V[F]
    vol = float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)
    # shells: connected components of the vertex graph
    import scipy.sparse as sp
    nv = len(V)
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(nv, nv))
    used = np.unique(F)
    ncomp, lab = sp.csgraph.connected_components(A, directed=False)
    n_shells = int(len(np.unique(lab[used])))
    return dict(n_triangles=int(len(F)), watertight=bool(boundary == 0 and nonman == 0 and orient),
                boundary_edges=boundary, nonmanifold_edges=nonman, orientation_ok=orient, volume=vol,
                n_shells=n_shells)


def stl_bytes(V: np.ndarray, F: np.ndarray, name: str = "amm") -> bytes:
    """Binary STL (little-endian float32), facet normals from the right-hand rule."""
    tri = V[F].astype(np.float64)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-300)
    head = name.encode("ascii", "replace")[:80].ljust(80, b" ")
    rec = np.zeros(len(tri), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = nrm, tri
    return head + struct.pack("<I", len(tri)) + rec.tobytes()


# ---------------------------------------------------------------------------------------------------------------
# screening
# ---------------------------------------------------------------------------------------------------------------
def _opening_removed(phase: np.ndarray, L_vox: float, pad: int) -> float:
    """Fraction of `phase` (periodic binary cell) in features thinner than L_vox voxels: the part not recovered by
    an opening with a ball of diameter L_vox. Distances are between voxel centres, so a ball centre must lie more
    than L/2 + 1/2 voxel from the nearest voxel of the other phase (a slab of k voxels keeps a centre iff k > L);
    the dilation back uses radius L/2 + 1/2 plus one voxel, so the one-voxel surface staircase is not counted as
    removed. Resolution: about one voxel."""
    if phase.sum() == 0:
        return 0.0
    P = np.pad(phase, pad, mode="wrap")
    r = 0.5 * L_vox + 0.5
    eroded = ndimage.distance_transform_edt(P) > r
    if not eroded.any():
        return 1.0
    opened = ndimage.distance_transform_edt(~eroded) <= r + 1.0
    c = (slice(pad, -pad),) * 3
    kept = (opened & P)[c]
    return float(1.0 - kept.sum() / phase.sum())


def min_feature(phase: np.ndarray, tol: float = FEATURE_TOL, step: float = 0.25) -> dict:
    """Estimated thinnest feature of a periodic binary phase, in voxels: the smallest L (bisection to `step` voxels)
    whose opening removes more than `tol` of the phase. Features at least L thick hold all but `tol` of it."""
    n = phase.shape[0]
    pad = n // 2 + 2
    curve = {}

    def rem(L):
        L = round(L, 4)
        if L not in curve:
            curve[L] = _opening_removed(phase, L, pad)
        return curve[L]

    lo, hi = 0.0, float(n)
    if rem(hi) <= tol:
        return dict(voxels=hi, removed=curve)
    while hi - lo > step:
        mid = 0.5 * (lo + hi)
        if rem(mid) <= tol:
            lo = mid
        else:
            hi = mid
    return dict(voxels=hi, removed=curve)


def _components(m: np.ndarray) -> dict:
    lab, n = ndimage.label(m)
    if n == 0:
        return dict(n_components=0, largest_fraction=0.0, spans=[False] * 3)
    vol = np.bincount(lab.ravel())[1:]
    big = int(np.argmax(vol)) + 1
    spans = [bool((np.take(lab, 0, axis=d) == big).any() and (np.take(lab, -1, axis=d) == big).any())
             for d in range(3)]
    return dict(n_components=int(n), largest_fraction=float(vol.max() / vol.sum()), spans=spans)


def screen(spec: dict, cell_size_m: float | None, printer_limit_m: float | None, limit_source: str,
           tiles: int = 3, resolution: int = 64, tile_resolution: int = 32, method: str = "auto",
           meshes: dict | None = None) -> dict:
    """Manufacturing screening of one design (see the module docstring). `meshes`: precomputed {"cell": (V, F,
    method), "tiled": (V, F, method)} in cell units, from `build`."""
    field, info = solid_field(spec, resolution)
    solid = field >= 0.5
    h = 1.0 / resolution
    a_mm = cell_size_m * 1e3 if cell_size_m else None
    out = dict(schema_version=SCREEN_SCHEMA, design=dict(kind=spec["kind"], params=spec["params"]),
               resolution=resolution, voxel=dict(cell_units=h, mm=a_mm * h if a_mm else None),
               cell_size_mm=a_mm, removed_islands_fraction=info["removed_fraction"], disclaimer=SCREEN_DISCLAIMER)
    # minimum feature, solid and void
    ms, mv = min_feature(solid), min_feature(~solid)
    feat = dict(tolerance=FEATURE_TOL, solid_est_cell_units=ms["voxels"] * h, void_est_cell_units=mv["voxels"] * h,
                solid_est_mm=ms["voxels"] * h * a_mm if a_mm else None,
                void_est_mm=mv["voxels"] * h * a_mm if a_mm else None,
                printer_limit_mm=printer_limit_m * 1e3 if printer_limit_m else None, limit_source=limit_source)
    if a_mm and printer_limit_m:
        L_vox = printer_limit_m * 1e3 / (a_mm * h)
        pad = resolution // 2 + 2
        feat["limit_voxels"] = L_vox
        feat["solid_thinner_than_limit"] = _opening_removed(solid, L_vox, pad)
        feat["void_narrower_than_limit"] = _opening_removed(~solid, L_vox, pad)
        feat["passed"] = bool(feat["solid_thinner_than_limit"] <= FEATURE_TOL)
        feat["void_passed"] = bool(feat["void_narrower_than_limit"] <= FEATURE_TOL)
        if L_vox < 2:
            feat["note"] = "printer limit below two voxels at this resolution: raise `resolution` for a sharper check"
    else:
        feat["passed"] = None
        feat["note"] = "needs the cell size and a printer limit (set_constraints cell_size; material or argument)"
    out["min_feature"] = feat
    # tiled connectivity (finite block, not periodic)
    blk = np.tile(solid, (tiles,) * 3)
    comp = _components(blk)
    out["tiled_connectivity"] = dict(tiles=tiles, **comp, passed=bool(comp["n_components"] == 1 and all(comp["spans"])))
    cell_comp = _components(solid)
    out["cell_connectivity"] = dict(**cell_comp, note="one cell cut at its walls, as a single printed cell")
    # watertight surfaces
    meshes = meshes or build(spec, tiles, resolution, tile_resolution, method)[0]
    wt = {}
    for k, (V, F, meth) in meshes.items():
        chk = mesh_check(V, F)
        n_cells = 1 if k == "cell" else tiles ** 3
        vox_vol = float((field >= 0.5).mean()) * n_cells
        chk.update(method=meth, voxel_volume_cell_units=vox_vol,
                   volume_rel_diff=(chk["volume"] - vox_vol) / vox_vol if vox_vol else None)
        wt[k] = chk
    out["watertight"] = dict(**wt, passed=bool(all(v["watertight"] for v in wt.values())))
    checks = [out["tiled_connectivity"]["passed"], out["watertight"]["passed"]]
    if feat["passed"] is not None:
        checks.append(feat["passed"])
    out["passed"] = bool(all(checks))
    out["complete"] = feat["passed"] is not None
    out["verdict"] = ("screen passed" if out["passed"] and out["complete"] else
                      "screen failed" if not out["passed"] else "screen incomplete (minimum feature not checked)")
    return out


def build(spec: dict, tiles: int = 3, resolution: int = 64, tile_resolution: int = 32, method: str = "auto"):
    """Surfaces in cell units: ({"cell": (V, F, method), "tiled": (V, F, method)}, cleaning info)."""
    field, info = solid_field(spec, resolution)
    Vc, Fc, mc = surface(field, 1.0 / resolution, method)
    if tile_resolution == resolution:
        ft = field
    else:
        ft, _ = solid_field(spec, tile_resolution)
    Vt, Ft, mt = surface(np.tile(ft, (tiles,) * 3), 1.0 / tile_resolution, method)
    return {"cell": (Vc, Fc, mc), "tiled": (Vt, Ft, mt)}, info


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
