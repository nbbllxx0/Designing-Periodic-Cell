"""Second atlas scan for the V6 targets (run before any V6 solve; NOTES.md section 1.3 and 2): pessimistic n_clear
(atlas cells clearing every target at the pessimistic end of the calibrated error ranges, the oracle's FEASIBLE
count) over E100_min x band ratio for the mount and over band ratio for the filter. No solve.
    python scripts/verify/v6/rescan_spec.py"""
import json
from pathlib import Path
import amm  # noqa: F401
from amm import atlas, tools, units

err = atlas.error_model(); dom = atlas.error_domain()
R = {nu: [(r, atlas.err_for(r["spec"], err)) for r in tools.atlas_rows(nu) if atlas.calibrated(r["spec"], dom)]
     for nu in (0.39, 0.3)}


def nclear(mat, a, tg):
    norm, _, _ = units.normalize(dict(material=mat, cell_size=[a * 1e3, "mm"], **tg))
    rows = R[units.MATERIALS[mat]["nu"]]
    ok = [r["spec"] for r, e in rows if atlas.slacks(r, norm, e, "pess")["min"] > 0]
    return len(ok), norm, ok


out = dict(mount={}, filter={})
for E in (60, 80, 100):
    for ratio in (1.2, 1.3, 1.4, 1.5):
        row = []
        for i in range(10, 60):
            flo = 500.0 * i
            n, norm, ok = nclear("PA12", 0.02, dict(E100_min=[E, "MPa"], gap={"f_lo": [flo, "Hz"], "f_hi": [ratio * flo, "Hz"]}))
            row.append(dict(f_lo_Hz=flo, n_clear=n, clear=ok))
        out["mount"][f"E{E}_r{ratio}"] = row
        print(E, ratio, [(r["f_lo_Hz"] / 1e3, r["n_clear"]) for r in row if r["n_clear"]][:10], flush=True)
for ratio in (1.1, 1.15, 1.2, 1.25):
    row = []
    for i in range(8, 60):
        flo = 2500.0 * i
        d = {}
        for m in ("PA12", "316L"):
            n, norm, ok = nclear(m, 0.010, dict(gap={"f_lo": [flo, "Hz"], "f_hi": [ratio * flo, "Hz"]}))
            d[m] = dict(n_clear=n, clear=ok, gap=norm["gap"])
        row.append(dict(f_lo_Hz=flo, **d))
    out["filter"][f"r{ratio}"] = row
    print("filter", ratio, [(r["f_lo_Hz"], r["PA12"]["n_clear"], r["316L"]["n_clear"]) for r in row
                            if r["PA12"]["n_clear"] and r["316L"]["n_clear"]], flush=True)
Path(__file__).resolve().parents[3].joinpath("results/verification/v6/spec_rescan.json").write_text(
    json.dumps(out, indent=1, default=float), encoding="utf-8")
