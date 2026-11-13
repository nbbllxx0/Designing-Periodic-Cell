"""V6 spec selection from the search atlas (no solve; CPU only). Written and run BEFORE any V6 design, certificate or
chain run. It only reads the atlas oracle (amm.atlas.oracle with the calibrated error model) to place the targets.

Rule (fixed before the scan, NOTES.md section 1):
  mount: PA12, a = 20 mm, block 6 x 6 x 6 cells (120 mm cube), load W = 3 kN, deflection <= 0.25 mm
         -> k_req = 12 kN/mm -> E100_min = k_req H / A = 100 MPa (uniaxial-stress estimate, lateral faces free).
         band [f_lo, 1.5 f_lo] in Hz; f_lo scanned on a 0.5 kHz grid. Chosen: the LOWEST f_lo whose atlas verdict is
         FEASIBLE with 3 <= n_clear <= 20 (feasible but not trivial: few atlas cells clear it at the pessimistic end).
  filter: gap-only, a = 10 mm in both PA12 and 316L, the same physical band [f_lo, 1.25 f_lo]; f_lo on a 5 kHz grid;
         chosen: the lowest f_lo FEASIBLE in BOTH materials (any n_clear >= 1).
    python scripts/verify/v6/select_spec.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import amm  # noqa: F401
from amm import atlas, tools, units

OUT = Path(__file__).resolve().parents[3] / "results" / "verification" / "v6" / "spec_selection.json"


def oracle(material, a_m, targets_phys):
    m = units.MATERIALS[material]
    req = dict(material=material, cell_size=[a_m * 1e3, "mm"], **targets_phys)
    norm, missing, _ = units.normalize(req)
    assert not missing, missing
    rows = tools.atlas_rows(m["nu"])
    o = atlas.oracle(rows, norm, top=5)
    return dict(norm=norm, verdict=o["verdict"], n_clear=o["n_clear"], n_possible=o["n_possible"],
                best=[dict(kind=b["spec"]["kind"], params=b["spec"]["params"], slack_pess=b["slack_pess"],
                           slack_nominal=b["slack_nominal"]) for b in o["best"][:5]])


def main():
    out = dict(mount=[], filter=[])
    a = 0.020
    E_min = 3000.0 / 0.25e-3 * (6 * a) / (6 * a) ** 2  # k_req H / A [Pa]
    print(f"mount: E100_min = {E_min/1e6:.2f} MPa")
    chosen = None
    for i in range(10, 60):
        flo = 500.0 * i
        tg = dict(E100_min=[E_min / 1e6, "MPa"], gap={"f_lo": [flo, "Hz"], "f_hi": [1.5 * flo, "Hz"]})
        r = oracle("PA12", a, tg)
        r["f_lo_Hz"], r["f_hi_Hz"] = flo, 1.5 * flo
        out["mount"].append(r)
        print(f"  [{flo/1e3:5.1f}, {1.5*flo/1e3:5.2f}] kHz f*=[{r['norm']['gap']['f_lo']:.3f},{r['norm']['gap']['f_hi']:.3f}]"
              f" {r['verdict']:22s} clear {r['n_clear']:3d} possible {r['n_possible']:3d}"
              f"  best {r['best'][0]['kind']} {r['best'][0]['params']} {r['best'][0]['slack_pess']:+.3f}")
        if chosen is None and r["verdict"] == "FEASIBLE" and 3 <= r["n_clear"] <= 20:
            chosen = r
    out["mount_chosen"] = chosen
    fch = None
    for i in range(4, 30):
        flo = 5000.0 * i
        rs = {}
        for mat in ("PA12", "316L"):
            tg = dict(gap={"f_lo": [flo, "Hz"], "f_hi": [1.25 * flo, "Hz"]})
            rs[mat] = oracle(mat, 0.010, tg)
        out["filter"].append(dict(f_lo_Hz=flo, f_hi_Hz=1.25 * flo, **rs))
        print(f"  filter [{flo/1e3:.0f}, {1.25*flo/1e3:.2f}] kHz: " + "; ".join(
            f"{k} f*=[{v['norm']['gap']['f_lo']:.3f},{v['norm']['gap']['f_hi']:.3f}] {v['verdict']} {v['n_clear']}"
            for k, v in rs.items()))
        if fch is None and all(v["verdict"] == "FEASIBLE" for v in rs.values()):
            fch = out["filter"][-1]
    out["filter_chosen"] = fch
    OUT.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print("chosen mount:", chosen and (chosen["f_lo_Hz"], chosen["f_hi_Hz"], chosen["n_clear"]))
    print("chosen filter:", fch and (fch["f_lo_Hz"], fch["f_hi_Hz"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
