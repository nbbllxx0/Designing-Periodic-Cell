"""Audit F06: independent FE check of amm certificates on 10 exact-geometry cells (grid-aligned cube_bars at
n = 20 and 40), 5 of them with a complete-gap claim, over the three material Poisson ratios. See indep_fe.py.

    run_indep.py amm      certificates of every cell with the current amm checker (cached)
    run_indep.py indep N  independent Q2 solves at n = N (static + spectra at Gamma, X, M, R)
    run_indep.py compare  -> results/verification/indep/summary.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import indep_fe  # noqa: E402
from amm import atlas, certify, geometry  # noqa: E402

OUT = ROOT / "results" / "verification" / "indep"
NUS = (0.3, 0.342, 0.39)
# (c, w, search-tier gap in f* or None); gaps from `evaluate` at nu 0.3 (search tier, 2026-11-06)
CELLS = [(0.5, 0.1, None), (0.5, 0.2, (0.429, 0.669)), (0.5, 0.3, None), (0.6, 0.1, None), (0.6, 0.2, (0.334, 0.769)),
         (0.6, 0.3, (0.584, 0.741)), (0.7, 0.2, None), (0.7, 0.3, (0.575, 0.760)), (0.8, 0.2, None),
         (0.8, 0.3, (0.463, 0.624))]
Q2_GAP_CLAIMS = [(0.5, 0.2, 0.4126, 0.5184), (0.6, 0.3, 0.5693, 0.6469), (0.7, 0.3, 0.5192, 0.6385)]
GAP_AT_SEARCH_NU = {(0.5, 0.2), (0.6, 0.3), (0.7, 0.3)}


def cells():
    out = []
    for i, (c, w, gap) in enumerate(CELLS):
        nu = NUS[i % 3]
        targets = {"E100_min": 1e-4, "G_min": 1e-4, "bulk_min": 1e-4}
        if gap:  # claim the middle half of the search-tier gap
            lo, hi = gap
            targets["gap"] = {"f_lo": round(lo + 0.25 * (hi - lo), 4), "f_hi": round(hi - 0.25 * (hi - lo), 4)}
        out.append(dict(name=f"cube_bars_c{c}_w{w}_nu{nu}", spec=atlas.make_spec("cube_bars", dict(c=c, w=w)),
                        nu=nu, targets=targets))
    # added 2026-11-06 after the first pass: three gap claims were made at nu != 0.3 (the search nu) and came out
    # undetermined, leaving 2 certified gaps to test. The same claims at nu = 0.3 add certified-gap cases.
    for c, w, (lo, hi) in [(c, w, g) for c, w, g in CELLS if g and (c, w) in GAP_AT_SEARCH_NU]:
        targets = {"E100_min": 1e-4, "G_min": 1e-4, "bulk_min": 1e-4,
                   "gap": {"f_lo": round(lo + 0.25 * (hi - lo), 4), "f_hi": round(hi - 0.25 * (hi - lo), 4)}}
        out.append(dict(name=f"cube_bars_c{c}_w{w}_nu0.3", spec=atlas.make_spec("cube_bars", dict(c=c, w=w)),
                        nu=0.3, targets=targets))
    # second addition (2026-11-06): those three were refuted by the Q2 spectra (band 7 below f_hi at Gamma); the
    # search tier shifts gap edges up by about 0.07-0.1. Claims set to the middle half of the Q2 n = 20 gap at
    # Gamma, X, M, R (band 6 max, band 7 min), frozen here, to obtain more certified gaps to test.
    for c, w, lo, hi in Q2_GAP_CLAIMS:
        out.append(dict(name=f"cube_bars_c{c}_w{w}_nu0.3_g2", spec=atlas.make_spec("cube_bars", dict(c=c, w=w)),
                        nu=0.3, targets={"E100_min": 1e-4, "G_min": 1e-4, "bulk_min": 1e-4,
                                         "gap": {"f_lo": lo, "f_hi": hi}}))
    return out


def run_amm():
    OUT.mkdir(parents=True, exist_ok=True)
    for cell in cells():
        f = OUT / f"{cell['name']}_amm.json"
        if f.exists():
            continue
        t0 = time.perf_counter()
        c = certify.certify(cell["spec"], cell["targets"], nu=cell["nu"], as_built=False)
        f.write_text(json.dumps(c, default=float), encoding="utf-8")
        print(cell["name"], c["verdict"], round(time.perf_counter() - t0, 1), "s", flush=True)


def run_indep(n: int, max_spectra_dofs: int = 400_000):
    OUT.mkdir(parents=True, exist_ok=True)
    for cell in cells():
        f = OUT / f"{cell['name']}_q2_n{n}.json"
        if f.exists():
            continue
        cov, _, info = geometry.design_cell(cell["spec"], n)
        assert set(map(float, set(cov.ravel().round(9)))) <= {0.0, 1.0}, "voxelization not exact"
        t0 = time.perf_counter()
        q = indep_fe.Q2Cell(cov, cell["nu"])
        res = dict(name=cell["name"], n=n, static=q.homogenize())
        res["static_s"] = round(time.perf_counter() - t0, 1)
        if "gap" in cell["targets"] and res["static"]["n_dofs"] <= max_spectra_dofs:
            a = json.loads((OUT / f"{cell['name']}_amm.json").read_text(encoding="utf-8"))
            nb = a["blocks"]["bloch"]["claim"]["below_band"]
            res["below_band"] = nb
            res["spectra"], res["eig_residual"] = {}, {}
            for name, kpi in indep_fe.HIGH_SYM.items():
                res["spectra"][name] = indep_fe.Q2Cell.spectrum(q, kpi, k_eig=nb + 4).tolist()
                res["eig_residual"][name] = q.last_eig_residual
        res["seconds"] = round(time.perf_counter() - t0, 1)
        f.write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(cell["name"], n, res["seconds"], "s", res["static"]["n_dofs"], "dofs", flush=True)


def compare():
    rows, missing = [], []
    for cell in cells():
        if not (OUT / f"{cell['name']}_amm.json").exists():
            missing.append(f"{cell['name']}_amm")
            continue
        a = json.loads((OUT / f"{cell['name']}_amm.json").read_text(encoding="utf-8"))
        q = a["blocks"]["static"]["convergence"]["quantities"]
        row = dict(name=cell["name"], nu=cell["nu"], amm_verdict=a["verdict"], checker=a.get("checker"), indep={})
        for n in (20, 40):
            f = OUT / f"{cell['name']}_q2_n{n}.json"
            if not f.exists():
                missing.append(f"{cell['name']}_q2_n{n}")
                continue
            r = json.loads(f.read_text(encoding="utf-8"))
            st = r["static"]
            chk = {k: dict(amm_lower=q[k]["lower"], amm_upper=q[k]["upper"], amm_ext=q[k]["extrapolated"],
                           indep_upper_bound=st[k],
                           necessary_check_passed=bool(q[k]["lower"] <= st[k] * (1 + 1e-9)),
                           indep_inside=bool(q[k]["lower"] <= st[k] <= q[k]["upper"]))
                   for k in ("E100", "G", "bulk")}
            chk["density"] = dict(amm=q["density"]["extrapolated"], exact=st["density"])
            ent = dict(static=chk, residual=st["residual"], n_dofs=st["n_dofs"])
            if "spectra" in r:
                cv = a["blocks"]["bloch"].get("convergence") or {}
                si = cv.get("safe_interval")
                nb = r["below_band"]
                below = max(v[nb - 1] for v in r["spectra"].values())
                above = min(v[nb] for v in r["spectra"].values())
                ent["gap"] = dict(claim=[cell["targets"]["gap"]["f_lo"], cell["targets"]["gap"]["f_hi"]],
                                  amm_safe_interval=si, amm_gap_verdict=a["blocks"]["bloch"]["verdict"]["verdict"],
                                  below_band=nb, indep_band_below_max_hs=below, indep_band_above_min_hs=above,
                                  upper_edge_check_passed=(None if not si else bool(above >= si[1] * (1 - 1e-9))),
                                  eig_residual_max=max(r["eig_residual"].values()),
                                  consistent_lower_edge=(None if not si else bool(below <= si[0])),
                                  claim_open_at_hs=bool(above >= cell["targets"]["gap"]["f_hi"]))
            row["indep"][f"n{n}"] = ent
        rows.append(row)
    (OUT / "summary.json").write_text(json.dumps(dict(rows=rows, missing=missing), indent=1), encoding="utf-8")
    print("missing results:", missing)
    for r in rows:
        for n, e in r["indep"].items():
            s = e["static"]
            print(r["name"], n, r["amm_verdict"], " ".join(f"{k}:{'ok' if s[k]['necessary_check_passed'] else 'FAIL'}"
                                                         f"({s[k]['amm_lower']:.4g}<= {s[k]['indep_upper_bound']:.4g})"
                                                         for k in ("E100", "G", "bulk")),
                  ("gap:" + str(e["gap"]["upper_edge_check_passed"]) + f" si={e['gap']['amm_safe_interval']} "
                   f"hs=({e['gap']['indep_band_below_max_hs']:.4f},{e['gap']['indep_band_above_min_hs']:.4f})")
                  if "gap" in e else "")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts" / "bench"))
    from e4 import GpuLock  # the project's exclusive solver lock: never alongside E4 jobs
    with GpuLock(f"run_indep {' '.join(sys.argv[1:])}"):
        {"amm": run_amm, "indep": lambda: run_indep(int(sys.argv[2])), "compare": compare}[sys.argv[1]]()
