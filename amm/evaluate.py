"""Search-tier evaluation: fast, approximate properties of a design spec, for use inside design loops.

Static: periodic homogenization at n_static (CPU, PARDISO). Bloch: band diagram on a coarse k-path at n_bloch
(GPU dense, complex64). Both use finite-cell partial voxels. In a batch, static solves run in a CPU thread pool
while the GPU computes bands (both release the GIL in native code). Results are NOT certificates; see `certify`.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from . import bloch, fem, geometry, homog
from .progress import checkpoint

KEEP = ("density", "C11", "C12", "C44", "E100", "nu100", "G", "bulk", "zener", "cubic_deviation", "min_eig")


def _static(cell, nu, keep_tensor=False):
    cov, sub, info = cell
    if info["n_components"] == 0 or not all(info["percolates"]):
        return dict(valid=False, reason="empty" if info["n_components"] == 0 else "does not percolate",
                    density=info["density"], percolates=info["percolates"])
    try:
        r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub, nu=nu))
    except Exception as e:
        return dict(valid=False, reason=f"solver error: {e}", density=info["density"])
    out = {k: r[k] for k in KEEP}
    if keep_tensor:  # the full homogenized tensor C* (6x6 Voigt, normalized by E_s), B1 2026-11-07
        out["C"] = r["C"]
    out.update(valid=bool(r["min_eig"] > 1e-8 and info["removed_fraction"] <= 0.01 and all(info["percolates"])),
               removed_fraction=info["removed_fraction"], percolates=info["percolates"], static_s=r["seconds"])
    return out


def _bands(cell, ks, nev, nu, device):
    cov, sub, info = cell
    if info["n_components"] == 0 or not all(info["percolates"]):
        # a non-percolating coarse mesh has spurious zero bands and fake gaps: report no gap
        return dict(gaps=[], best_rel_gap=0.0, bloch_valid=False, bloch_density=info["density"])
    t = time.perf_counter()
    f = bloch.GPUBands(fem.build_mesh(cov, sub=sub, nu=nu), device=device)(ks, nev=nev)
    g = bloch.gaps(f)
    return dict(gaps=g[:3], best_rel_gap=g[0]["rel"] if g else 0.0, bands=f, bloch_density=info["density"],
                bloch_valid=True, bloch_s=round(time.perf_counter() - t, 3))


def evaluate_batch(specs: list[dict], n_static: int = 20, n_bloch: int = 10, n_fine: int = 60, npts: int = 3,
                   nev: int = 12, nu: float = 0.3, device: str = "cuda", workers: int = 2,
                   keep_bands: bool = False, keep_tensor: bool = False) -> list[dict]:
    """n_fine: one sub-sample grid shared by both resolutions (must be divisible by n_static and n_bloch).
    keep_tensor: also return the full 6x6 C* ("C"). device "cuda" falls back to the CPU when no CUDA device is
    available (bloch.resolve_device; the row then says bloch_device "cpu", not bit-identical to the GPU)."""
    ks, _ = bloch.kpath(npts)
    device = bloch.resolve_device(device)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fut, bl = [], []
        for i, s in enumerate(specs):
            checkpoint("search tier: design", design=i + 1, n_designs=len(specs))
            cells = geometry.design_cells(s, (n_bloch, n_static), n_fine)
            fut.append(ex.submit(_static, cells[n_static], nu, keep_tensor))
            bl.append(_bands(cells[n_bloch], ks, nev, nu, device))
        st = [f.result() for f in fut]
    per_cell = round((time.perf_counter() - t0) / len(specs), 3)
    out = []
    for s, a, b in zip(specs, st, bl):
        if not keep_bands:
            b.pop("bands", None)
        row = dict(spec=s, **a, **b, batch_seconds_per_cell=per_cell)
        if device != "cuda":
            row["bloch_device"] = device
        out.append(row)
    return out


def evaluate(spec: dict, **kw) -> dict:
    return evaluate_batch([spec], **kw)[0]
