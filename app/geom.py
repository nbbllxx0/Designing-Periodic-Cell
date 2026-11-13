"""Preview geometry for the GUI: the level-set fields of amm/geometry.py (same formulas, copied so that mock mode never
imports amm), a binary voxel mask at voxel centres, its boundary surface as a triangle mesh, and an STL writer.

This is a *preview*: the certified model is amm's anti-aliased finite-cell voxelization at the certificate
resolutions. In live mode the server takes the mask from amm.geometry.make(coverage=False) instead, so preview and
solver geometry coincide there.
"""
from __future__ import annotations

import itertools
import struct

import numpy as np


def _grid(n: int):
    c = (np.arange(n) + 0.5) / n
    return np.meshgrid(c, c, c, indexing="ij")


def _tpms(kind: str, n: int) -> np.ndarray:
    X, Y, Z = (2 * np.pi * g for g in _grid(n))
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
    if kind == "sc":
        segs = [((0, .5, .5), (1, .5, .5)), ((.5, 0, .5), (.5, 1, .5)), ((.5, .5, 0), (.5, .5, 1))]
    elif kind == "bcc":
        segs = [((0, 0, 0), (1, 1, 1)), ((1, 0, 0), (0, 1, 1)), ((0, 1, 0), (1, 0, 1)), ((0, 0, 1), (1, 1, 0))]
    elif kind == "octet":
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


def _box(X, Y, Z, hx, hy, hz):
    return np.maximum(np.maximum(np.abs(X) - hx, np.abs(Y) - hy), np.abs(Z) - hz)


FAMILY_OF = {"gyroid": "tpms", "schwarz_p": "tpms", "diamond": "tpms", "iwp": "tpms", "sc": "struts", "bcc": "struts",
             "octet": "struts", "cube_bars": "resonator", "sphere_ligaments": "resonator"}


def mask(kind: str, params: dict, n: int = 40) -> np.ndarray:
    """Binary solid mask (n,n,n) at voxel centres."""
    fam = FAMILY_OF[kind]
    if fam == "tpms":
        f = _tpms(kind, n)
        phi = np.abs(f) if params.get("mode", "network") == "sheet" else f
        flat = np.sort(phi.ravel())
        thr = flat[min(max(int(round(float(params["density"]) * flat.size)), 1), flat.size - 1)]
        return phi <= thr
    if fam == "struts":
        P = np.stack([g.ravel() for g in _grid(n)], axis=1)
        segs = _segments(kind)
        d2 = np.full(len(P), np.inf)
        for a, b in segs:
            ab = b - a
            t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
            q = P - a - t[:, None] * ab
            d2 = np.minimum(d2, np.einsum("ij,ij->i", q, q))
        phi = np.sqrt(d2) - float(params["r"])
        R = float(params.get("R", 0) or 0)
        if R > 0:
            dn = np.min(np.linalg.norm(P[:, None, :] - _nodes(kind)[None], axis=2), axis=1) - R
            phi = np.minimum(phi, dn)
        return (phi <= 0).reshape(n, n, n)
    c, w = float(params["c"]), float(params["w"])
    X, Y, Z = (g - 0.5 for g in _grid(n))
    if kind == "cube_bars":
        core = _box(X, Y, Z, c / 2, c / 2, c / 2)
        bars = np.minimum(np.minimum(_box(X, Y, Z, 1, w / 2, w / 2), _box(X, Y, Z, w / 2, 1, w / 2)),
                          _box(X, Y, Z, w / 2, w / 2, 1))
    else:
        core = np.sqrt(X**2 + Y**2 + Z**2) - c
        bars = np.minimum(np.minimum(np.sqrt(Y**2 + Z**2), np.sqrt(X**2 + Z**2)), np.sqrt(X**2 + Y**2)) - w / 2
    return np.minimum(core, bars) <= 0


def boundary_mesh(m: np.ndarray, periodic: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Faces between solid and void voxels as triangles in cell coordinates [0,1]^3: (vertices (V,3), faces (F,3)).
    periodic=False closes the surface at the cell walls (a printable single cell); True omits wall faces whose
    periodic neighbour is solid (for seamless tiling)."""
    n = m.shape[0]
    h = 1.0 / n
    verts, faces = [], []
    pad = np.pad(m, 1, mode="wrap" if periodic else "constant", constant_values=False)
    corner = {  # axis, sign -> the 4 corners of the face (unit cube coords), counter-clockwise seen from outside
        (0, 1): [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], (0, -1): [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
        (1, 1): [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)], (1, -1): [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
        (2, 1): [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], (2, -1): [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)],
    }
    core = pad[1:-1, 1:-1, 1:-1]
    for (ax, sg), cs in corner.items():
        sl = [slice(1, -1)] * 3
        sl[ax] = slice(1 + sg, pad.shape[ax] - 1 + sg)
        nb = pad[tuple(sl)]
        idx = np.argwhere(core & ~nb)
        if not len(idx):
            continue
        base = sum(len(v) for v in verts)
        q = (idx[:, None, :] + np.array(cs)[None]) * h  # (k,4,3)
        verts.append(q.reshape(-1, 3))
        k = np.arange(len(idx)) * 4 + base
        faces.append(np.stack([np.stack([k, k + 1, k + 2], 1), np.stack([k, k + 2, k + 3], 1)], 1).reshape(-1, 3))
    if not verts:
        return np.zeros((0, 3)), np.zeros((0, 3), int)
    return np.concatenate(verts), np.concatenate(faces)


def stl_bytes(verts: np.ndarray, faces: np.ndarray, scale: float = 1.0, tiles: int = 1,
              name: str = "amm preview") -> bytes:
    """Binary STL of the mesh tiled tiles^3 times, scaled to physical length (e.g. the cell size in mm)."""
    tri = verts[faces] * scale  # (F,3,3)
    if tiles > 1:
        offs = np.array(list(itertools.product(range(tiles), repeat=3)), float) * scale
        tri = (tri[None] + offs[:, None, None, :]).reshape(-1, 3, 3)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-30)
    head = name.encode()[:80].ljust(80, b" ")
    rec = np.zeros(len(tri), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = nrm, tri
    return head + struct.pack("<I", len(tri)) + rec.tobytes()


def preview(kind: str, params: dict, n: int = 32) -> dict:
    m = mask(kind, params, n)
    v, f = boundary_mesh(m, periodic=False)
    return dict(kind=kind, params=params, n=n, density_preview=float(m.mean()), vertices=v.round(5).ravel().tolist(),
                faces=f.ravel().tolist(), note="preview mask at voxel centres; the certificate uses amm's "
                                              "anti-aliased finite-cell voxelization")
