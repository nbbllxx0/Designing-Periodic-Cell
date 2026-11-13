"""Materials and unit conversion between physical requests and the solvers' normalized quantities.

Normalization: stiffness / E_s, frequency f* = f a / c_t with c_t = sqrt(E_s / (2 (1 + nu_s)) / rho_s), lengths / a.
Material values are typical datasheet / handbook values for additively manufactured parts; they are inputs of a
request, not claims, and the paper must cite the source used for each.
"""
from __future__ import annotations

import math

MATERIALS = {
    # name: E [Pa], nu, rho [kg/m^3], process, min printable feature [m], dimensional tolerance [m]
    "PA12": dict(E=1.70e9, nu=0.39, rho=1010.0, process="SLS", min_feature=0.8e-3, tolerance=0.15e-3),
    "Ti6Al4V": dict(E=113.8e9, nu=0.342, rho=4430.0, process="LPBF", min_feature=0.3e-3, tolerance=0.05e-3),
    "316L": dict(E=193.0e9, nu=0.30, rho=8000.0, process="LPBF", min_feature=0.3e-3, tolerance=0.05e-3),
    "AlSi10Mg": dict(E=70.0e9, nu=0.33, rho=2670.0, process="LPBF", min_feature=0.4e-3, tolerance=0.05e-3),
}

STIFFNESS_KEYS = ("E100_min", "E100_max", "G_min", "bulk_min")
LENGTH_UNITS = {"m": 1.0, "mm": 1e-3, "um": 1e-6, "cm": 1e-2, "in": 0.0254}
PRESSURE_UNITS = {"Pa": 1.0, "kPa": 1e3, "MPa": 1e6, "GPa": 1e9, "psi": 6894.757}
FREQ_UNITS = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6}


def c_t(mat: dict) -> float:
    return math.sqrt(mat["E"] / (2 * (1 + mat["nu"])) / mat["rho"])


def normalize(request: dict) -> tuple[dict, list[str], dict]:
    """Physical request -> (normalized targets, missing information, context).

    request keys (all optional):
      material: name in MATERIALS or dict(E, nu, rho)
      cell_size: [value, unit]
      density_max / density_min: solid fraction (dimensionless)
      E100_min, E100_max, G_min, bulk_min: [value, unit] in pressure units, or a bare number = fraction of E_s
      nu100_min, nu100_max: dimensionless
      gap: {"f_lo": [v, unit], "f_hi": [v, unit]} in Hz units, or bare numbers = normalized f*
    Missing material makes physical stiffness unconvertible; missing cell size makes physical frequencies
    unconvertible. Those are reported in `missing` (a reason to ask, not to guess).
    """
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


def to_physical(norm: dict, mat: dict, a: float | None = None) -> dict:
    """Normalized results -> physical (Pa, Hz) for reports."""
    out = {}
    for k in ("E100", "G", "bulk", "C11", "C12", "C44"):
        if k in norm:
            out[k + "_Pa"] = norm[k] * mat["E"]
    if a is not None:
        for k in ("f_lo", "f_hi"):
            if k in norm:
                out[k + "_Hz"] = norm[k] * c_t(mat) / a
    return out
