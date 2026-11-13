"""Small numerical helpers for the GUI, importable without amm.

* `normalize`, `c_t`: a line-by-line mirror of amm/units.py (materials read from its source by toolspec), so that
  mock mode converts physical targets exactly as the tool contract does. tests/test_app.py checks the mirror
  against recorded `set_target` results.
* design validation: mirror of amm.atlas.{box, valid, make_spec}.
* cubic stiffness: Voigt matrix, compliance, directional Young's modulus E(n), its extremes and the Zener ratio.
* bands: k-path ticks of the search tier (amm.bloch.kpath with npts per leg) and complete gaps of a band array.
"""
from __future__ import annotations

import math

import numpy as np

from . import toolspec

LENGTH_UNITS = {"m": 1.0, "mm": 1e-3, "um": 1e-6, "cm": 1e-2, "in": 0.0254}
PRESSURE_UNITS = {"Pa": 1.0, "kPa": 1e3, "MPa": 1e6, "GPa": 1e9, "psi": 6894.757}
FREQ_UNITS = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6}
STIFFNESS_KEYS = ("E100_min", "E100_max", "G_min", "bulk_min")
R_GAP = 0.03


def materials() -> dict:
    return toolspec.materials()


def c_t(mat: dict) -> float:
    return math.sqrt(mat["E"] / (2 * (1 + mat["nu"])) / mat["rho"])


def normalize(request: dict) -> tuple[dict, list[str], dict]:
    """Mirror of amm.units.normalize: physical request -> (normalized targets, missing, context)."""
    MATERIALS = materials()
    t, missing, ctx = {}, [], {}
    mat = request.get("material")
    if isinstance(mat, str):
        if mat not in MATERIALS:
            missing.append(f"material '{mat}' unknown (known: {', '.join(MATERIALS)})")
            mat = None
        else:
            ctx["material_name"] = request["material"]
            mat = MATERIALS[mat]
    ctx["material"] = mat
    a = None
    if request.get("cell_size") is not None:
        v, u = request["cell_size"]
        a = v * LENGTH_UNITS[u]
        ctx["cell_size_m"] = a
    for k in ("density_max", "density_min", "nu100_min", "nu100_max"):
        if k in request:
            t[k] = float(request[k])
    for k in STIFFNESS_KEYS:
        if k in request:
            v = request[k]
            if isinstance(v, (int, float)):
                t[k] = float(v)
            elif mat is None:
                missing.append(f"{k} given in {v[1]} but no material: cannot normalize by E_s")
            else:
                t[k] = v[0] * PRESSURE_UNITS[v[1]] / mat["E"]
    if "gap" in request:
        g = {}
        for e in ("f_lo", "f_hi"):
            v = request["gap"][e]
            if isinstance(v, (int, float)):
                g[e] = float(v)
            elif mat is None or a is None:
                missing.append(f"gap.{e} given in {v[1]} but " + ("no material" if mat is None else "no cell size")
                               + ": cannot convert to f* = f a / c_t")
            else:
                g[e] = v[0] * FREQ_UNITS[v[1]] * a / c_t(mat)
        if len(g) == 2:
            t["gap"] = g
    ctx["nu_s"] = mat["nu"] if mat else None
    return t, missing, ctx


# ---- designs (mirror of amm.atlas) ----------------------------------------------------------------------------
def family_of(kind: str) -> str:
    for fam, kinds in toolspec.families()["families"].items():
        if kind in kinds:
            return fam
    raise ValueError(f"unknown kind {kind!r}")


def box(kind: str) -> dict:
    return {k: tuple(v) for k, v in toolspec.families()["families"][family_of(kind)][kind]["params"].items()}


def valid(kind: str, p: dict) -> bool:
    if kind == "cube_bars":
        return p["w"] <= p["c"] - 0.04
    if kind == "sphere_ligaments":
        return p["w"] <= 2 * p["c"] - 0.02
    if family_of(kind) == "struts":
        return p["R"] == 0.0 or p["R"] >= p["r"] + R_GAP
    return True


def make_spec(kind: str, p: dict, mode: str | None = None) -> dict:
    fam = family_of(kind)
    params = {k: float(round(v, 6)) for k, v in p.items()}
    if fam == "tpms":
        params["mode"] = mode
    return dict(family=fam, kind=kind, params=params)


def design_spec(design: dict) -> dict:
    """Mirror of amm.tools.Session._design_spec (raises ValueError with the same messages)."""
    kind = design["kind"]
    p = dict(design["params"])
    fam = family_of(kind)
    mode = p.pop("mode", None)
    if fam == "tpms" and mode not in ("network", "sheet"):
        raise ValueError("TPMS design needs params.mode in ['network', 'sheet']")
    try:
        p = {k: float(v) for k, v in p.items()}
    except (TypeError, ValueError):
        raise ValueError("design parameters must be numbers (plus mode for TPMS)")
    b = box(kind)
    if set(p) != set(b):
        raise ValueError(f"{kind} takes parameters {sorted(b)} (got {sorted(p)})")
    for k, (lo, hi) in b.items():
        if not lo <= p[k] <= hi:
            raise ValueError(f"{kind}.{k} = {p[k]} outside the family box [{lo}, {hi}]")
    if not valid(kind, p):
        raise ValueError(f"{kind} parameters {p} violate the family's validity rule")
    return make_spec(kind, p, mode)


# ---- cubic stiffness -------------------------------------------------------------------------------------------
def voigt_cubic(C11: float, C12: float, C44: float) -> np.ndarray:
    C = np.zeros((6, 6))
    C[:3, :3] = C12
    np.fill_diagonal(C[:3, :3], C11)
    C[3, 3] = C[4, 4] = C[5, 5] = C44
    return C


def tensor_summary(C) -> dict:
    """Mirror of amm.tensor.summary (numpy only; mock mode never imports amm): directional Young's moduli from the
    full tensor (1/E(n) = m^T inv(C) m, m = (n1^2, n2^2, n3^2, n2 n3, n1 n3, n1 n2)), nu12, Voigt and Reuss bulk
    and shear averages, eigenvalues."""
    C = np.asarray(C, float)
    S = np.linalg.inv(C)

    def e(n):
        n = np.asarray(n, float) / np.linalg.norm(n)
        m = np.array([n[0] ** 2, n[1] ** 2, n[2] ** 2, n[1] * n[2], n[0] * n[2], n[0] * n[1]])
        return float(1.0 / (m @ S @ m))
    KV = float((C[0, 0] + C[1, 1] + C[2, 2] + 2 * (C[0, 1] + C[0, 2] + C[1, 2])) / 9)
    GV = float((C[0, 0] + C[1, 1] + C[2, 2] - (C[0, 1] + C[0, 2] + C[1, 2]) + 3 * (C[3, 3] + C[4, 4] + C[5, 5])) / 15)
    KR = float(1 / (S[0, 0] + S[1, 1] + S[2, 2] + 2 * (S[0, 1] + S[0, 2] + S[1, 2])))
    GR = float(15 / (4 * (S[0, 0] + S[1, 1] + S[2, 2]) - 4 * (S[0, 1] + S[0, 2] + S[1, 2])
                     + 3 * (S[3, 3] + S[4, 4] + S[5, 5])))
    return dict(E100=e((1, 0, 0)), E110=e((1, 1, 0)), E111=e((1, 1, 1)), nu12=float(-S[0, 1] / S[0, 0]),
                bulk_voigt=KV, bulk_reuss=KR, shear_voigt=GV, shear_reuss=GR,
                eigenvalues=[float(x) for x in np.linalg.eigvalsh(0.5 * (C + C.T))])


def young_directional(C11: float, C12: float, C44: float, n: np.ndarray) -> np.ndarray:
    """E(n) of a cubic material for unit directions n (..., 3): 1/E = S11 - 2 (S11 - S12 - S44/2) J(n),
    J = n1^2 n2^2 + n2^2 n3^2 + n3^2 n1^2."""
    d = (C11 - C12) * (C11 + 2 * C12)
    S11, S12, S44 = (C11 + C12) / d, -C12 / d, 1.0 / C44
    n = np.asarray(n, float)
    n = n / np.linalg.norm(n, axis=-1, keepdims=True)
    J = (n[..., 0] ** 2 * n[..., 1] ** 2 + n[..., 1] ** 2 * n[..., 2] ** 2 + n[..., 2] ** 2 * n[..., 0] ** 2)
    return 1.0 / (S11 - 2 * (S11 - S12 - S44 / 2) * J)


def cubic_summary(C11: float, C12: float, C44: float) -> dict:
    """Derived cubic quantities (normalized by E_s): E100, E110, E111, nu100, G (= C44), bulk, Zener ratio."""
    E = young_directional(C11, C12, C44, np.array([[1, 0, 0], [1, 1, 0], [1, 1, 1]], float))
    return dict(C11=C11, C12=C12, C44=C44, E100=float(E[0]), E110=float(E[1]), E111=float(E[2]),
                nu100=C12 / (C11 + C12), G=C44, bulk=(C11 + 2 * C12) / 3, zener=2 * C44 / (C11 - C12),
                E_max=float(E.max()), E_min=float(E.min()))


# ---- bands -----------------------------------------------------------------------------------------------------
SC_PATH = ("G", "X", "M", "G", "R", "X")


def kpath_ticks(n_k: int) -> list[tuple[int, str]]:
    """Ticks of amm.bloch.kpath for a band array with n_k points (npts per leg = (n_k - 1) / 5)."""
    legs = len(SC_PATH) - 1
    npts = (n_k - 1) // legs
    if npts * legs + 1 != n_k:
        return []
    return [(i * npts, lab) for i, lab in enumerate(SC_PATH)]


def complete_gaps(bands, min_rel: float = 0.0) -> list[dict]:
    """Mirror of amm.bloch.gaps: complete gaps between consecutive bands over the sampled k, widest first."""
    b = np.asarray(bands, float)
    out = []
    for j in range(b.shape[1] - 1):
        lo, hi = float(b[:, j].max()), float(b[:, j + 1].min())
        if hi > lo:
            rel = 2 * (hi - lo) / (hi + lo)
            if rel >= min_rel:
                out.append(dict(below_band=j + 1, f_lo=lo, f_hi=hi, rel=rel))
    return sorted(out, key=lambda g: -g["rel"])
