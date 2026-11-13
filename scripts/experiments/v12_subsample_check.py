"""V12 (audit-loop round 2, 2026-11-09): geometry sub-sampling refinement at the finest certificate level
(theory reviewer #1).

The acceptance model integrates each voxel with s^3 anti-aliased sub-samples, s = max(2, ceil(N_FINE / n)) with
N_FINE = 96, so the geometry sampling is not refined in step with the element size. For the three engineering
certificates, recompute at the finest level with N_FINE doubled (192):
  * static: E100 at the finest static level, grid phase 0, against the certificate's remaining error e;
  * Bloch: the two gap edges at n = 40 at the certificate's extreme wave vectors, against the edge guard's
    remaining error.
Each quantity is first recomputed with the default N_FINE to confirm that the stored value is reproduced.

    python scripts/experiments/v12_subsample_check.py
Writes results/verification/v12/subsample_check.json. CPU only (PARDISO), no LLM.
"""
import json
import time
from pathlib import Path

import numpy as np

import amm  # noqa: F401
from amm import bloch, geometry, homog
from amm.certify import _mesh

ROOT = Path(__file__).resolve().parents[2]
VER = ROOT / "results/verification"
OUT = VER / "v12"
CERTS = (("mount_PA12", "v6/case1/session_design/certificates/7db650ec44d50a1d_08d26401ae0bf0dc.json", 0.39),
         ("filter_PA12", "v6/case2/session_PA12/certificates/e5519f4fdbef64db_e212dc39bc22b626.json", 0.39),
         ("filter_316L", "v6/case2/session_316L/certificates/f1d00ed043a926f1_0dc7c12bea6f73f4.json", 0.3))


def static_E100(spec, n, nu):
    m, _ = _mesh(spec, n, nu)
    return homog.homogenize(mesh=m)["E100"]


def edges_at(spec, n, nu, k_lo, k_hi, f_lo, f_hi):
    m, _ = _mesh(spec, n, nu)
    ic = bloch.InertiaCounter(m)
    try:
        lo = max(ic.edge(np.pi * np.asarray(k), f_lo, "below") for k in k_lo)
        hi = min(ic.edge(np.pi * np.asarray(k), f_hi, "above") for k in k_hi)
    finally:
        ic.free()
    return lo, hi


def with_fine(nfine, fn, *a):
    old = geometry.N_FINE
    geometry.N_FINE = nfine
    try:
        return fn(*a)
    finally:
        geometry.N_FINE = old


def main():
    rows = []
    for name, cert, nu in CERTS:
        t0 = time.perf_counter()
        c = json.loads((VER / cert).read_text())
        spec = c["spec"]
        st = c["blocks"]["static"]
        nmax = max(st["used"])
        q = st["convergence"]["quantities"]["E100"]
        stored = st["resolutions"][str(nmax)]["E100"]
        base = with_fine(96, static_E100, spec, nmax, nu)
        fine = with_fine(192, static_E100, spec, nmax, nu)
        b = c["blocks"]["bloch"]
        conv = b["convergence"]
        k_lo, k_hi = b["edge_k_kept"]["lo"], b["edge_k_kept"]["hi"]
        f_lo, f_hi = b["claim"]["f_lo"], b["claim"]["f_hi"]
        st40 = conv["edges"]["40"]
        e_base = with_fine(96, edges_at, spec, 40, nu, k_lo, k_hi, f_lo, f_hi)
        e_fine = with_fine(192, edges_at, spec, 40, nu, k_lo, k_hi, f_lo, f_hi)
        row = dict(case=name, spec=spec, nu=nu,
                   static=dict(n=nmax, s_default=geometry.supersample(nmax),
                               s_doubled=max(2, int(np.ceil(192 / nmax))), stored=stored, recomputed=base,
                               doubled=fine, change_rel=(fine - base) / base,
                               remaining_rel=q["remaining"] / q["extrapolated"],
                               change_over_remaining=abs(fine - base) / q["remaining"]),
                   bloch=dict(n=40, s_default=geometry.supersample(40), s_doubled=max(2, int(np.ceil(192 / 40))),
                              stored=st40, recomputed=list(e_base), doubled=list(e_fine),
                              change_rel=[(e_fine[i] - e_base[i]) / e_base[i] for i in range(2)],
                              remaining=[conv["lower_edge"].get("remaining"), conv["upper_edge"].get("remaining")],
                              phase_spread=[conv["lower_edge"].get("phase_spread"),
                                            conv["upper_edge"].get("phase_spread")]),
                   seconds=round(time.perf_counter() - t0, 1))
        rows.append(row)
        print(json.dumps(dict(case=name, static_change_pct=round(100 * row["static"]["change_rel"], 3),
                              static_remaining_pct=round(100 * row["static"]["remaining_rel"], 3),
                              edge_change_pct=[round(100 * x, 3) for x in row["bloch"]["change_rel"]],
                              stored_vs_recomputed_static=stored - base,
                              stored_vs_recomputed_edges=[st40[i] - e_base[i] for i in range(2)],
                              seconds=row["seconds"])), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "subsample_check.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
