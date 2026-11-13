"""T7_v6.csv and acceptance.json from the V6 result files.
    python scripts/verify/v6/build_t7.py"""
from __future__ import annotations

import csv
import json
from pathlib import Path

V6 = Path(__file__).resolve().parents[3] / "results" / "verification" / "v6"
ES = {"PA12": 1.70e9, "316L": 193e9}


def J(p):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def row_for(case, item, sd, recheck, replay, macro=None, chains=None, extra_req=""):
    s = J(sd / "summary.json")
    if s is None:
        return None
    mat = s["config"]["material"]
    d = s["released"]
    cs = s["certificate_summary"] or {}
    cert_s = sum(c["seconds"] for c in s["certify"])
    tg = s["calls"]["set_target"]["result"]
    norm = tg["normalized"]
    ev = next((x for x in s["calls"]["evaluate"]["result"]["results"] if x["design"] == d), None)
    hz = ev["bands"]["hz_per_f_star"] if ev and ev.get("bands") else None
    st = (cs.get("static") or {}).get("bounds", {})
    gap = cs.get("gap") or {}
    sc = s["calls"]["screen_manufacturing"]["result"]
    req = []
    if "E100_min" in norm:
        req.append(f"E100 >= {norm['E100_min'] * ES[mat] / 1e6:.1f} MPa")
    if "gap" in norm:
        req.append(f"complete gap {norm['gap']['f_lo'] * hz / 1e3:.2f}-{norm['gap']['f_hi'] * hz / 1e3:.2f} kHz")
    if extra_req:
        req.append(extra_req)
    r = dict(case=case, item=item, material=mat, cell_mm=s["config"]["cell_size_mm"], requirement="; ".join(req),
             design=f"{d['kind']} " + " ".join(f"{k}={v}" for k, v in d["params"].items()) if d else "none",
             certify_calls=len(s["certify"]), verdict=cs.get("verdict"), robust_as_built=cs.get("robust"),
             density_upper=st.get("density", {}).get("upper"),
             E100_guarded_lower_MPa=st["E100"]["lower"] * ES[mat] / 1e6 if "E100" in st and "E100_min" in norm else None,
             E100_margin_pct=(100 * (st["E100"]["lower"] / norm["E100_min"] - 1)) if "E100" in st and "E100_min" in norm else None,
             G_guarded_lower_MPa=st["G"]["lower"] * ES[mat] / 1e6 if "G" in st and "E100_min" in norm else None,
             gap_safe_kHz=(f"{gap['safe_interval'][0] * hz / 1e3:.2f}-{gap['safe_interval'][1] * hz / 1e3:.2f}"
                           if gap.get("safe_interval") else None),
             gap_margin_lo_pct=(100 * (norm["gap"]["f_lo"] / gap["safe_interval"][0] - 1)) if gap.get("safe_interval") else None,
             gap_margin_hi_pct=(100 * (gap["safe_interval"][1] / norm["gap"]["f_hi"] - 1)) if gap.get("safe_interval") else None,
             screen=sc["verdict"], min_solid_mm=round(sc["min_feature"]["solid_est_mm"], 3),
             min_channel_mm=round(sc["min_feature"]["void_est_mm"], 3),
             printer_limit_mm=sc["min_feature"]["printer_limit_mm"],
             tiled_connected=sc["tiled_connectivity"]["passed"], watertight=sc["watertight"]["passed"],
             replay_exact=(replay or {}).get("exact"),
             time_session_s=s["seconds_total"], time_certify_s=round(cert_s, 1))
    if macro:
        r.update(k_hom_kN_mm=round(macro["A2"]["k_kN_per_mm"], 3), deflection_mm=round(macro["A2"]["deflection_mm"], 4),
                 deflection_margin_pct=round(100 * (0.25 / macro["A2"]["deflection_mm"] - 1), 2),
                 size_ratio_3x3x3_same_n32=round(macro["size_effect"]["ratio_same_n"]["n32"], 4),
                 deflection_size_corrected_mm=round(macro["A2s"]["size_corrected_deflection_mm"], 4),
                 time_macro_s=macro["seconds"])
    if chains:
        for n, c in chains.items():
            if c:
                r[f"T_long_band_mean_dB_n{n}"] = round(c["band_metrics"]["longitudinal"]["mean_dB"], 2)
                r[f"T_shear_band_mean_dB_n{n}"] = round(c["band_metrics"]["shear_x"]["mean_dB"], 2)
        r["time_chain_s"] = round(sum(c["seconds"] for c in chains.values() if c), 1)
    if recheck:
        dd = recheck["static"]["diff_extrapolated"]
        r.update(recheck_passed=recheck["passed"], recheck_density_diff_pct=round(100 * dd["density"], 3),
                 recheck_E100_diff_pct=round(100 * dd["E100"], 3),
                 recheck_static_verdict=(recheck["static"]["verdict"] or {}).get("verdict"),
                 recheck_gap_verdict=(recheck.get("gap") or {}).get("verdict", {}).get("verdict"),
                 recheck_gap_safe_kHz=(f"{recheck['gap']['safe_interval'][0] * hz / 1e3:.2f}-"
                                       f"{recheck['gap']['safe_interval'][1] * hz / 1e3:.2f}"
                                       if recheck.get("gap") and recheck["gap"].get("safe_interval")
                                       and recheck["gap"]["safe_interval"][0] is not None else None),
                 time_recheck_s=recheck["seconds"])
    return r


def main():
    c1 = V6 / "case1"
    ch = {lab: {n: J(c1 / f"chain_{lab}_n{n}.json") for n in (16, 24)} for lab in ("design", "reference")}
    rows = [
        row_for("1 mount", "design", c1 / "session_design", J(c1 / "recheck_design.json"), J(c1 / "replay_design.json"),
                J(c1 / "macro_design.json"), ch["design"], "W 1.8 kN, deflection <= 0.25 mm (6x6x6 block)"),
        row_for("1 mount", "reference", c1 / "session_reference", J(c1 / "recheck_reference.json"),
                J(c1 / "replay_reference.json"), J(c1 / "macro_reference.json"), ch["reference"], "no gap in band"),
    ]
    for m in ("PA12", "316L"):
        rows.append(row_for("2 filter", m, V6 / "case2" / f"session_{m}", J(V6 / "case2" / f"recheck_{m}.json"),
                            J(V6 / "case2" / f"replay_{m}.json")))
    rows = [r for r in rows if r]
    if len(rows) >= 2 and "k_hom_kN_mm" in rows[1]:
        rows[1]["k_over_design"] = round(rows[1]["k_hom_kN_mm"] / rows[0]["k_hom_kN_mm"], 4)
        for n in (16, 24):
            for pol in ("long", "shear"):
                k = f"T_{pol}_band_mean_dB_n{n}"
                rows[0][f"A3_delta_{pol}_dB_n{n}"] = round(rows[0][k] - rows[1][k], 2)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(V6 / "T7_v6.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    print(f"T7_v6.csv: {len(rows)} rows, {len(keys)} columns")


if __name__ == "__main__":
    main()
