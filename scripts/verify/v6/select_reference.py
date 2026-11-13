"""Reference design for Case 1 (NOTES.md 1.5 and deviation 1): no complete gap in the band, similar stiffness.

    python scripts/verify/v6/select_reference.py

Reads the design session summary (released design and its evaluate row), ranks the strut and TPMS atlas cells at
nu = 0.39 without a complete gap (rel >= 1 %) overlapping the band by |E100_corr - E100_corr(design)|, where
E100_corr = search-tier E100 / (1 + median search-tier error of the family; amm.atlas error model), ties to TPMS,
and writes the first 3 as candidates into case1/config_reference.json and case1/reference_selection.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import amm  # noqa: F401
from amm import atlas, tools

V6 = Path(__file__).resolve().parents[3] / "results" / "verification" / "v6"


def corr(row_or_spec, E, err):
    spec = row_or_spec["spec"] if "spec" in row_or_spec else row_or_spec
    return E / (1 + atlas.err_for(spec, err).get("median", {}).get("E100", 0.0))


def main():
    s = json.loads((V6 / "case1" / "session_design" / "summary.json").read_text(encoding="utf-8"))
    d = s["released"]
    norm = s["calls"]["set_target"]["result"]["normalized"]
    flo, fhi = norm["gap"]["f_lo"], norm["gap"]["f_hi"]
    ev = next(x for x in s["calls"]["evaluate"]["result"]["results"] if x["design"] == d)
    err = atlas.error_model()
    dspec = atlas.make_spec(d["kind"], {k: v for k, v in d["params"].items() if k != "mode"}, d["params"].get("mode"))
    target = corr(dspec, ev["E100"], err)
    dom = atlas.error_domain()
    cands = []
    for r in tools.atlas_rows(0.39):
        if r["spec"]["family"] not in ("struts", "tpms") or not r.get("valid") or not atlas.calibrated(r["spec"], dom):
            continue
        if any(g["f_lo"] < fhi and g["f_hi"] > flo for g in atlas.row_gaps(r, 0.01)):
            continue
        Ec = corr(r, r["E100"], err)
        cands.append(dict(design=dict(kind=r["spec"]["kind"], params=r["spec"]["params"]), E100_atlas=r["E100"],
                          E100_corr=Ec, rel=Ec / target - 1, family=r["spec"]["family"],
                          gaps=[(g["f_lo"], g["f_hi"]) for g in atlas.row_gaps(r, 0.01)][:2]))
    cands.sort(key=lambda c: (abs(c["rel"]), 0 if c["family"] == "tpms" else 1))
    out = dict(design=d, design_E100_eval=ev["E100"], design_E100_corr=target, band_f_star=[flo, fhi],
               n_candidates=len(cands), first=cands[:10])
    (V6 / "case1" / "reference_selection.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    cfg = dict(root="results/verification/v6/case1/session_reference", material="PA12", cell_size_mm=20,
               targets={"E100_min": {"value": 60, "unit": "MPa"}}, note="V6 case 1 reference: same stiffness, no gap",
               top=5, certify_max=3, candidates=[c["design"] for c in cands[:3]],
               export=dict(tiles=3, resolution=64, tile_resolution=32))
    (V6 / "case1" / "config_reference.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    for c in cands[:5]:
        print(c["design"], f"E100 atlas {c['E100_atlas']:.5f} corr {c['E100_corr']:.5f} rel {c['rel']:+.3f}")
    print("design", d, f"eval E100 {ev['E100']:.5f} corr {target:.5f}")


if __name__ == "__main__":
    main()
