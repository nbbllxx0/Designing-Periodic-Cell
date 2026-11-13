"""Tables of batch 2 (plan item A1): T1, T7, T10, T12, T14 and the T15 hook, from result files only.

Run through `make_all.py`. Same conventions as tables.py: every number shown is registered in the claims ledger with
its source file and the field or expression it came from. Numbers that exist only in a NOTES file are read with
`grab`, which fails the run if the quoted text is no longer in the file (so a table cannot drift from its source).
"""
from __future__ import annotations

import ast
import collections
import csv
import json
import re
from pathlib import Path

from common import ROOT, Ledger, fnum, read_csv, read_json, read_text, write_table

S = "scripts/paper/tables2.py"

V2 = "results/verification/v2"
V6 = "results/verification/v6"
T15_SRC = "results/verification/v10/T15_v10.csv"   # written by V10 (another work package); read only if present


def grab(L: Ledger, asset: str, item: str, path: str, rx: str, unit: str = "", note: str = "", group: int = 1,
         flags=0) -> str:
    """Value matched by the regex `rx` in the text file `path` (group `group`), registered as verified."""
    txt = read_text(path)
    m = re.search(rx, txt, flags)
    assert m, f"{asset}/{item}: pattern {rx!r} not found in {path}"
    v = " ".join(m.group(group).split())
    L.add(asset, item, v, path, f"text matching /{rx}/", unit=unit, script=S, note=note)
    return v


def _pytest_summary(path: str) -> str:
    """Last pytest summary line of a log ('174 passed, 1 skipped, ... in 404.56s')."""
    lines = [ln for ln in read_text(path).splitlines() if re.search(r"\d+ passed", ln)]
    assert lines, f"no pytest summary in {path}"
    return lines[-1].strip(" =")


# ============================================================================================================ T12
def t12_matrix(L: Ledger):
    src, msrc = f"{V2}/T12_v2.csv", f"{V2}/matrix.csv"
    t12 = read_csv(src)
    mat = read_csv(msrc)
    ifs = ["lib", "mcp", "gui", "gui-edge", "cli"]
    # recount from matrix.csv and compare with T12_v2.csv (both are V2 outputs; a mismatch is a conflict)
    cnt = collections.Counter((r["group"], r["interface"], r["result"]) for r in mat)
    rows = []
    for r in t12:
        grp = r["capability group"]
        cells = []
        for i in ifs:
            v = r[f"{i} (pass+refused/rows)"]
            cells.append(v)
            if grp != "All rows" and v != "-":
                ok = cnt[(grp, i, "pass")] + cnt[(grp, i, "refused as expected")]
                tot = sum(n for (g, ii, _), n in cnt.items() if g == grp and ii == i)
                if f"{ok}/{tot}" != v:
                    L.conflict("T12", f"{grp}.{i}", {src: v, f"{msrc} (recount)": f"{ok}/{tot}"}, script=S)
                else:
                    L.add("T12", f"{grp}.{i}", v, src, f"'{i} (pass+refused/rows)'; recount of {msrc} agrees",
                          script=S)
        fail_cause = []
        for k, lab in (("fail: V2 expectation or design", "V2 expectation/design"), ("fail: amm", "amm"),
                       ("fail: app", "app/")):
            if r[k] not in ("0", ""):
                fail_cause.append(f"{r[k]} {lab}")
            L.add("T12", f"{grp}.{k}", r[k], src, k, script=S)
        for k in ("total rows", "pass", "refused as expected", "fail"):
            L.add("T12", f"{grp}.{k}", r[k], src, k, script=S)
        if grp == "All rows":
            rows.append("## All capability groups")
        rows.append([grp] + cells + [r["total rows"], r["pass"], r["refused as expected"], r["fail"],
                                     "; ".join(fail_cause) or "-"])
    # totals recount
    tot = collections.Counter(r["result"] for r in mat)
    for k in ("pass", "refused as expected", "fail"):
        L.add("T12", f"recount.{k}", tot[k], msrc, f"count result == {k!r}", status="derived", script=S)
    n_checks = len({(r["scenario"], r["check"]) for r in mat})
    L.add("T12", "n_rows", len(mat), msrc, "rows", status="derived", script=S)
    L.add("T12", "n_checks", n_checks, msrc, "distinct (scenario, check)", status="derived", script=S)
    fails = [r for r in mat if r["result"] == "fail"]
    v2fails = [r for r in fails if not r["cause"].startswith("app/")]
    appfails = [r for r in fails if r["cause"].startswith("app/")]
    L.add("T12", "fail.v2_expectation_or_design", len(v2fails), msrc, "fail rows whose cause is not app/",
          status="derived", script=S)
    L.add("T12", "fail.app", len(appfails), msrc, "fail rows whose cause starts with app/", status="derived",
          script=S)
    # how each of the 31 V2 errors was resolved
    replaced = [r for r in v2fails if "Replaced by" in r["cause"]]
    posthoc = [r for r in v2fails if "posthoc" in r["cause"]]
    noneed = [r for r in v2fails if r not in replaced and r not in posthoc]
    add_rows = [r for r in mat if r["scenario"].startswith(("S16", "S17"))]
    add_ok = sum(r["result"] in ("pass", "refused as expected") for r in add_rows)
    add_pass = sum(r["result"] == "pass" for r in add_rows)
    L.add("T12", "v2err.replaced_by_addendum", len(replaced), msrc, "fail rows with 'Replaced by' in cause",
          status="derived", script=S)
    L.add("T12", "v2err.checked_post_hoc", len(posthoc), msrc, "fail rows citing posthoc_checks.json",
          status="derived", script=S)
    L.add("T12", "v2err.no_rerun_needed", len(noneed), msrc, "remaining V2-error fail rows (verdict predicate held)",
          status="derived", script=S)
    L.add("T12", "addendum.rows", len(add_rows), msrc, "rows of scenarios S16*, S17*", status="derived", script=S)
    L.add("T12", "addendum.met", add_ok, msrc, "S16/S17 rows pass or refused as expected", status="derived", script=S)
    L.add("T12", "addendum.pass", add_pass, msrc, "S16/S17 rows pass", status="derived", script=S)
    ph = read_json(f"{V2}/posthoc_checks.json")
    L.add("T12", "posthoc.holds", ph[0]["holds"], f"{V2}/posthoc_checks.json", "[0].holds", script=S)
    rp = read_csv(f"{V2}/replays.csv")
    nonprobe = [r for r in rp if r["tag"] != "probe"]
    exact_np = sum(r["exact"] == "True" for r in nonprobe)
    probe = [r for r in rp if r["tag"] == "probe"]
    L.add("T12", "replay.v2_logs", f"{exact_np}/{len(nonprobe)}", f"{V2}/replays.csv",
          "exact == True among rows with tag != probe", status="derived", script=S)
    L.add("T12", "replay.probe_exact", f"{sum(r['exact'] == 'True' for r in probe)}/{len(probe)}",
          f"{V2}/replays.csv", "exact == True among tag == probe", status="derived", script=S)
    cc = read_json(f"{V2}/cert_consistency.json")["certificates"]
    hashes = {k: v["result_hash"] for k, v in cc.items()}
    L.add("T12", "cert_identity.result_hashes", "; ".join(f"{k} {v}" for k, v in hashes.items()),
          f"{V2}/cert_consistency.json", "certificates.*.result_hash", script=S)
    same = len(set(hashes.values())) == 1
    gui_fix = grab(L, "T12", "post_v2_fix.gui_health", f"{V2}/NOTES.md",
                   r"`gui_health` row: `app/server\.py` `/api/health` now reports ([^;]+);")
    probe_bugs = grab(L, "T12", "probe.amm_bugs", f"{V2}/NOTES.md", r"It found three amm bugs: ([^(]+)\(")
    tests = grab(L, "T12", "tests.after_v2", f"{V2}/NOTES.md", r"Full test suite under the lock: (\d+ passed, \d+ skipped)")
    notes = [
        f"Source: `{src}` (counts per capability group and interface), recounted from `{msrc}` ({len(mat)} rows, "
        f"{n_checks} distinct checks); cell = (pass + refused as expected) / rows. V2 protocol and expectations were "
        f"written before the run (`{V2}/NOTES.md` section 1; `expectations.csv`, `expectations_transport.csv`).",
        f"Totals: {tot['pass']} pass, {tot['refused as expected']} refused as expected, {tot['fail']} fail. "
        f"{len(v2fails)} failures are V2 expectation or design errors (amm was correct) and {len(appfails)} is an app/ "
        "bug; no failure is an amm bug. Every failed row stays in the matrix with its cause.",
        f"The {len(v2fails)} V2 errors: {len(replaced)} rows were replaced by an addendum (S16, S17) whose expectations "
        f"were written before it ran; its {len(add_rows)} rows all met their expectation ({add_pass} pass, "
        f"{add_ok - add_pass} refused as expected). {len(posthoc)} row (`combo_export`) had a wrong JSON path; the "
        f"corrected predicate holds on the same report.json (`posthoc_checks.json`, checked post hoc). "
        f"{len(noneed)} rows (`fam_all_bounds`) had a wrong `n_cells` expectation while the verdict predicate held; "
        "they were not re-run.",
        f"The app/ failure (`gui_health`: /api/health showed the mock schema and code hash in live mode) was fixed "
        f"after V2 (\"Post-V2 fixes\" in the V2 NOTES): /api/health now reports {gui_fix}. The matrix row stays "
        "`fail` as recorded.",
        f"Before run 1, a probe on the library found three amm bugs ({probe_bugs.strip()}); they were fixed before any "
        "matrix row ran (results/software/NOTES_V2_fixes.md).",
        f"Replay: {exact_np} of {len(nonprobe)} V2 session logs replay exactly; the static PA12 certificate is "
        f"{'identical' if same else 'NOT identical'} through MCP, GUI, CLI and tutorial 02 (result hash "
        f"{next(iter(hashes.values()))}). Test suite after V2: {tests} (the skip passed when rerun alone).",
        "Interfaces: lib = Python library (`amm.tools.Session`); mcp = MCP server driven by a client with no LLM; gui = "
        "live GUI HTTP API; gui-edge = clicks in headless Edge; cli = `python -m amm.cli` (added in V2).",
    ]
    return write_table("T12_capability_matrix", "Capability and interface acceptance matrix (V2)",
                       ["Capability group", "lib", "mcp", "gui", "gui-edge", "cli", "Rows", "Pass", "Refused",
                        "Fail", "Fail cause"], rows, notes, colspec="p{4.2cm}lllllrrrrp{2.6cm}",
                       label="tab:capability")


# ============================================================================================================ T7
_ES = {"PA12": 1.70e9, "316L": 193e9}   # E_s of the V6 materials (Pa), as in scripts/verify/v6/build_t7.py


def _t7_full():
    """Full-precision values of the numeric T7 columns, recomputed from the V6 JSON files with the formulas of
    scripts/verify/v6/build_t7.py. T7_v6.csv stores rounded values (2-4 decimals); formatting a display value from
    them rounds twice (final asset audit, finding 9), so every displayed number is formatted from these instead.
    Returns ([dict per T7 column order], {column: source file per row})."""
    c1, c2 = f"{V6}/case1", f"{V6}/case2"
    specs = [("design", f"{c1}/session_design", f"{c1}/recheck_design.json", f"{c1}/macro_design.json", "design"),
             ("reference", f"{c1}/session_reference", f"{c1}/recheck_reference.json", f"{c1}/macro_reference.json",
              "reference"),
             ("PA12", f"{c2}/session_PA12", f"{c2}/recheck_PA12.json", None, None),
             ("316L", f"{c2}/session_316L", f"{c2}/recheck_316L.json", None, None)]
    out, srcs = [], []
    for _lab, sd, rc, mc, chain in specs:
        s = read_json(f"{sd}/summary.json")
        mat = s["config"]["material"]
        cs = s["certificate_summary"] or {}
        st = (cs.get("static") or {}).get("bounds", {})
        norm = s["calls"]["set_target"]["result"]["normalized"]
        gap = cs.get("gap") or {}
        sc = s["calls"]["screen_manufacturing"]["result"]
        r, src = {}, {}
        sp = f"{sd}/summary.json"
        if "E100" in st and "E100_min" in norm:
            r["E100_guarded_lower_MPa"] = st["E100"]["lower"] * _ES[mat] / 1e6
            r["E100_margin_pct"] = 100 * (st["E100"]["lower"] / norm["E100_min"] - 1)
            src["E100_guarded_lower_MPa"] = src["E100_margin_pct"] = sp
        if "density" in st:
            r["density_upper"] = st["density"]["upper"]
            src["density_upper"] = sp
        if gap.get("safe_interval"):
            r["gap_margin_lo_pct"] = 100 * (norm["gap"]["f_lo"] / gap["safe_interval"][0] - 1)
            r["gap_margin_hi_pct"] = 100 * (gap["safe_interval"][1] / norm["gap"]["f_hi"] - 1)
            src["gap_margin_lo_pct"] = src["gap_margin_hi_pct"] = sp
        r["min_solid_mm"] = sc["min_feature"]["solid_est_mm"]
        r["printer_limit_mm"] = sc["min_feature"]["printer_limit_mm"]
        r["time_session_s"] = s["seconds_total"]
        r["time_certify_s"] = sum(c["seconds"] for c in s["certify"])
        for k in ("min_solid_mm", "printer_limit_mm", "time_session_s", "time_certify_s"):
            src[k] = sp
        if mc:
            m = read_json(mc)
            r["k_hom_kN_mm"] = m["A2"]["k_kN_per_mm"]
            r["deflection_mm"] = m["A2"]["deflection_mm"]
            r["deflection_margin_pct"] = 100 * (0.25 / m["A2"]["deflection_mm"] - 1)
            r["size_ratio_3x3x3_same_n32"] = m["size_effect"]["ratio_same_n"]["n32"]
            for k in ("k_hom_kN_mm", "deflection_mm", "deflection_margin_pct", "size_ratio_3x3x3_same_n32"):
                src[k] = mc
        if chain:
            for n in (16, 24):
                cp = f"{c1}/chain_{chain}_n{n}.json"
                ch = read_json(cp)
                r[f"T_long_band_mean_dB_n{n}"] = ch["band_metrics"]["longitudinal"]["mean_dB"]
                r[f"T_shear_band_mean_dB_n{n}"] = ch["band_metrics"]["shear_x"]["mean_dB"]
                src[f"T_long_band_mean_dB_n{n}"] = src[f"T_shear_band_mean_dB_n{n}"] = cp
        rj = read_json(rc)
        dd = rj["static"]["diff_extrapolated"]
        r["recheck_density_diff_pct"] = 100 * dd["density"]
        r["recheck_E100_diff_pct"] = 100 * dd["E100"]
        src["recheck_density_diff_pct"] = src["recheck_E100_diff_pct"] = rc
        out.append(r)
        srcs.append(src)
    d, ref = out[0], out[1]
    d["k_over_design"] = None
    ref["k_over_design"] = ref["k_hom_kN_mm"] / d["k_hom_kN_mm"]
    srcs[1]["k_over_design"] = f"{srcs[1]['k_hom_kN_mm']}; {srcs[0]['k_hom_kN_mm']}"
    for n in (16, 24):
        for pol in ("long", "shear"):
            k = f"T_{pol}_band_mean_dB_n{n}"
            d[f"A3_delta_{pol}_dB_n{n}"] = d[k] - ref[k]
            srcs[0][f"A3_delta_{pol}_dB_n{n}"] = f"{srcs[0][k]}; {srcs[1][k]}"
    return out, srcs


FINE = "results/verification/v15/filters.json"
FINE_RC = "results/verification/v16/recheck_PA12.json"
FINE_RC_316L = "results/verification/v16/recheck_316L.json"
REJUDGE = "results/verification/v19/rejudge.json"


def _released_note(L: Ledger) -> str:
    """The table records the V6 run under its own rules; this note gives the filter verdicts of the released checker
    (results/verification/v14 rescore; the v15 finer gap check re-judged after the order-test fix, v19)."""
    fine = read_json(REJUDGE)["filters"]
    for k, c in fine.items():
        L.add("T7", f"filter_{k}.verdict_finer_gap_check", c["after"], REJUDGE, f"filters.{k}.after", script=S)
    rc = read_json(FINE_RC)
    L.add("T7", "filter_PA12.export_recheck_finer", rc["overall"], FINE_RC, "overall", script=S)
    if (ROOT / FINE_RC_316L).exists():
        rc3 = read_json(FINE_RC_316L)
        L.add("T7", "filter_316L.export_recheck_finer", rc3["overall"], FINE_RC_316L, "overall", script=S)
        tail = f"; the exported 316L cell ({FINE_RC_316L}) is {rc3['overall']}."
    else:
        tail = "; the 316L export recheck was not rerun."
    return ("Released rules (amm 0.2.0, after the V6 run): re-judged from the stored solves "
            "(results/verification/v14/engineering.json), the PA12 filter has no safe upper edge and the 316L bars "
            "span 2.4 voxels at n = 40, so both are undetermined; the finer gap check (counted n = 30 and 40, edges at "
            f"n = 60; {FINE}, re-judged in {REJUDGE}) gives PA12 {fine['PA12']['after']} and 316L "
            f"{fine['316L']['after']}. The mount certificates hold. The exported PA12 cell, rechecked at the same "
            f"resolutions ({FINE_RC}), is {rc['overall']}" + tail)


def t7_cases(L: Ledger):
    src = f"{V6}/T7_v6.csv"
    rows_csv = read_csv(src)
    full, full_src = _t7_full()
    # every full-precision value must round to the stored CSV value (else the CSV and the JSON disagree: conflict)
    for i, (r, f) in enumerate(zip(rows_csv, full)):
        for k, x in f.items():
            if x is None or r.get(k) in ("", None):
                continue
            stored = r[k]
            dec = len(stored.split(".")[1]) if "." in stored else 0
            # build_t7 formed the A3 differences and k ratio from operands it had already rounded (2 and 3 decimals)
            tol = 0.011 if k.startswith("A3_delta") else 2e-4 if k == "k_over_design" else 0.6 * 10 ** -dec
            if abs(round(x, dec) - float(stored)) > tol:
                L.conflict("T7", f"row{i}.{k}", {src: stored, full_src[i][k] + " (full precision)": x}, script=S)
    # the CSV rows are replaced by the full-precision values for every numeric column the table formats
    rows_csv = [dict(r, **{k: ("" if x is None else repr(float(x))) for k, x in f.items()}) for r, f in zip(rows_csv, full)]
    cols = [("mount design", rows_csv[0]), ("mount reference", rows_csv[1]), ("filter PA12", rows_csv[2]),
            ("filter 316L", rows_csv[3])]
    for name, r in cols:
        assert r["case"].startswith(("1", "2")), r
    # cross-checks against the per-run JSON files (V6 built T7_v6.csv from them with build_t7.py)
    summ = {"mount design": f"{V6}/case1/session_design/summary.json",
            "mount reference": f"{V6}/case1/session_reference/summary.json",
            "filter PA12": f"{V6}/case2/session_PA12/summary.json",
            "filter 316L": f"{V6}/case2/session_316L/summary.json"}
    for name, r in cols:
        s = read_json(summ[name])
        cs = s["certificate_summary"]
        if r["E100_guarded_lower_MPa"]:
            v = cs["E100_MPa"]
            if abs(v - float(r["E100_guarded_lower_MPa"])) > 1e-3:
                L.conflict("T7", f"{name}.E100", {src: r["E100_guarded_lower_MPa"], summ[name]: v}, script=S)
        if cs["verdict"] != r["verdict"]:
            L.conflict("T7", f"{name}.verdict", {src: r["verdict"], summ[name]: cs["verdict"]}, script=S)
        if str(cs["robust"]) != r["robust_as_built"]:
            L.conflict("T7", f"{name}.robust", {src: r["robust_as_built"], summ[name]: cs["robust"]}, script=S)
    md = read_json(f"{V6}/case1/macro_design.json")
    if abs(md["A2"]["k_kN_per_mm"] - float(cols[0][1]["k_hom_kN_mm"])) > 1e-3:
        L.conflict("T7", "mount.k", {src: cols[0][1]["k_hom_kN_mm"], f"{V6}/case1/macro_design.json":
                                     md["A2"]["k_kN_per_mm"]}, script=S)
    for lab, n in (("design", 16), ("design", 24), ("reference", 16), ("reference", 24)):
        ch = read_json(f"{V6}/case1/chain_{lab}_n{n}.json")
        r = cols[0][1] if lab == "design" else cols[1][1]
        for dk, col in (("longitudinal", f"T_long_band_mean_dB_n{n}"), ("shear_x", f"T_shear_band_mean_dB_n{n}")):
            if abs(ch["band_metrics"][dk]["mean_dB"] - float(r[col])) > 0.01:
                L.conflict("T7", f"{lab}.{col}", {src: r[col], f"chain_{lab}_n{n}.json": ch["band_metrics"][dk]["mean_dB"]},
                           script=S)

    def val(r, k, fmt="{}", unit=""):
        v = r.get(k, "")
        if v in ("", None):
            return "-"
        try:
            x = float(v)
            s = fmt.format(x)
        except ValueError:
            s = v
        return s + (f" {unit}" if unit else "")

    # E100 guarded lower in physical units; margin; gap; flags
    items = [
        ("Material, cell a", lambda r: f"{r['material']}, {r['cell_mm']} mm", "material, cell_mm"),
        ("Requirement", lambda r: r["requirement"], "requirement"),
        ("Design (search tier suggestion certified)", lambda r: r["design"], "design"),
        ("Certify calls / verdict", lambda r: f"{r['certify_calls']} / {r['verdict']}", "certify_calls, verdict"),
        ("Guarded E100 lower (margin)", lambda r: "-" if not r["E100_guarded_lower_MPa"] else
         f"{float(r['E100_guarded_lower_MPa']):.2f} MPa ({float(r['E100_margin_pct']):+.1f} %)",
         "E100_guarded_lower_MPa, E100_margin_pct"),
        ("Density (upper bound)", lambda r: val(r, "density_upper", "{:.3f}"), "density_upper"),
        ("Guarded safe gap (margins below / above claim)", lambda r: "-" if not r["gap_safe_kHz"] else
         f"{r['gap_safe_kHz']} kHz ({float(r['gap_margin_lo_pct']):.1f} % / {float(r['gap_margin_hi_pct']):.0f} %)",
         "gap_safe_kHz, gap_margin_lo_pct, gap_margin_hi_pct"),
        ("As-built ±0.01 a robust (flag)", lambda r: "yes" if r["robust_as_built"] == "True" else "**no**",
         "robust_as_built"),
        ("Screening: min solid / limit", lambda r: f"{r['screen']}: {float(r['min_solid_mm']):.2f} / "
         f"{float(r['printer_limit_mm']):.1f} mm", "screen, min_solid_mm, printer_limit_mm"),
        ("Tiled connected / watertight", lambda r: f"{r['tiled_connected']} / {r['watertight']}",
         "tiled_connected, watertight"),
        ("Mount stiffness, 6×6×6 homogenized (guarded C*)", lambda r: "-" if not r["k_hom_kN_mm"] else
         f"{float(r['k_hom_kN_mm']):.3f} kN/mm; {float(r['deflection_mm']):.4f} mm "
         f"({float(r['deflection_margin_pct']):+.1f} %)", "k_hom_kN_mm, deflection_mm, deflection_margin_pct"),
        ("3×3×3 voxel / homogenized, same n = 32", lambda r: val(r, "size_ratio_3x3x3_same_n32", "{:.4f}"),
         "size_ratio_3x3x3_same_n32"),
        ("6-cell band-mean T, long. n16 / n24", lambda r: "-" if not r["T_long_band_mean_dB_n16"] else
         f"{float(r['T_long_band_mean_dB_n16']):.1f} / {float(r['T_long_band_mean_dB_n24']):.1f} dB",
         "T_long_band_mean_dB_n16, _n24"),
        ("6-cell band-mean T, shear n16 / n24", lambda r: "-" if not r["T_shear_band_mean_dB_n16"] else
         f"{float(r['T_shear_band_mean_dB_n16']):.1f} / {float(r['T_shear_band_mean_dB_n24']):.1f} dB",
         "T_shear_band_mean_dB_n16, _n24"),
        ("Design − reference, long. / shear (n16; n24)", lambda r: "-" if not r["A3_delta_long_dB_n16"] else
         f"{float(r['A3_delta_long_dB_n16']):.1f} / {float(r['A3_delta_shear_dB_n16']):.1f}; "
         f"{float(r['A3_delta_long_dB_n24']):.1f} / {float(r['A3_delta_shear_dB_n24']):.1f} dB",
         "A3_delta_*"),
        ("Reference k / design k", lambda r: val(r, "k_over_design", "{:.3f}"), "k_over_design"),
        ("Exported STL recheck: density, E100 vs certificate", lambda r:
         f"{r['recheck_passed']}: {float(r['recheck_density_diff_pct']):+.2f} %, "
         f"{float(r['recheck_E100_diff_pct']):+.2f} %", "recheck_passed, recheck_*_diff_pct"),
        ("STL recheck verdicts (static; gap, safe)", lambda r: f"{r['recheck_static_verdict'] or '-'}; "
         f"{r['recheck_gap_verdict'] or '-'}" + (f", {r['recheck_gap_safe_kHz']} kHz" if r['recheck_gap_safe_kHz']
                                                 else ""), "recheck_static_verdict, recheck_gap_*"),
        ("Session replay exact", lambda r: r["replay_exact"], "replay_exact"),
        ("Wall time: session (certify)", lambda r: f"{float(r['time_session_s']):.0f} s "
         f"({float(r['time_certify_s']):.0f} s)", "time_session_s, time_certify_s"),
    ]
    rows = []
    import fnmatch
    for lab, fn, field in items:
        cells = [fn(r) for _, r in cols]
        rows.append([lab] + cells)
        toks = [t.strip() for t in field.split(",")]
        for i, ((name, _), c) in enumerate(zip(cols, cells)):
            if c != "-":
                js = sorted({p for k, ps in full_src[i].items()
                             if any(fnmatch.fnmatchcase(k, t) or (t.startswith("_") and k.endswith(t)) for t in toks)
                             for p in ps.split("; ")})
                L.add("T7", f"{name}.{lab}", c, "; ".join(js) if js else src,
                      field + (" (full precision from the JSON files; T7_v6.csv agrees after rounding)" if js else ""),
                      script=S)
    # as-built details from the certificates (the flags the table marks)
    flags = []
    for name, cert_glob, E_s in (("mount design", "case1/session_design/certificates/*.json", 1.70e9),
                                 ("mount reference", "case1/session_reference/certificates/688ee*.json", 1.70e9),
                                 ("filter 316L", "case2/session_316L/certificates/*.json", 193e9)):
        p = sorted((ROOT / V6).glob(cert_glob))[0]
        rp = p.relative_to(ROOT).as_posix()
        c = json.loads(p.read_text(encoding="utf-8"))
        ab = c["blocks"]["as_built"]["cases"]
        failed = [k for k, v in ab.items() if not v["passed"]]
        for k in failed:
            why = []
            if not ab[k].get("static_ok", True):
                why.append(f"E100 {ab[k]['E100'] * E_s / 1e6:.1f} MPa")
                L.add("T7", f"{name}.as_built.{k}.E100_MPa", f"{ab[k]['E100'] * E_s / 1e6:.1f}", rp,
                      f"blocks.as_built.cases.{k}.E100 x E_s", status="derived", unit="MPa", script=S)
            if ab[k].get("gap_ok") is False:
                why.append("gap counts fail")
                L.add("T7", f"{name}.as_built.{k}.gap_ok", False, rp, f"blocks.as_built.cases.{k}.gap_ok", script=S)
            flags.append(f"{name}: {'erosion' if k == 'erode' else 'dilation'} by 0.01 a fails ({', '.join(why)})")
    pa = rows_csv[2]
    # chain damping, A3 threshold and the interpretation floor, each traced to its file (finding 10)
    etas = {}
    for lab in ("design", "reference"):
        for n in (16, 24):
            p = f"{V6}/case1/chain_{lab}_n{n}.json"
            etas[p] = read_json(p)["eta"]
    assert len(set(etas.values())) == 1, etas
    eta = next(iter(etas.values()))
    L.add("T7", "chain.eta", eta, "; ".join(etas), "eta (hysteretic loss factor; equal in all four chain files)",
          script=S)
    v6n = f"{V6}/NOTES.md"
    a3_thr = grab(L, "T7", "A3.threshold_dB", v6n, r"design minus reference <= \*\*(-\d+) dB\*\*", unit="dB",
                  note="A3 acceptance threshold (V6 NOTES 1.8, fixed before the case-1 solver runs)")
    floor_db = grab(L, "T7", "chain.interpretation_floor_dB", v6n, r"In-band levels below about (-\d+) dB have",
                    unit="dB", note="interpretation limit of the periodic-slab model (V6 NOTES section 9)")
    # V6 deviations 1-5 (NOTES section 7): each heading must still be in the file
    devs = [("1", "reference ranking", "before the reference was selected: candidates ranked by atlas E100 corrected "
                                      "for the family's median search-tier error instead of raw atlas E100; A4 "
                                      "unchanged"),
            ("2", "size-effect ratio", "after the first design macro run: the size-effect ratio is taken against the "
                                       "cell's own C* at the same n (the first estimator mixed in discretization "
                                       "bias); A2s is a reported flag, A2 unaffected"),
            ("3", "STL re-voxelization anti-aliasing", "after the first static rows of the design recheck, before any "
                                                       "recheck verdict: binary ray-parity samples replaced by "
                                                       "anti-aliased fractions; the aborted run is kept"),
            ("4", "case-1 sessions rerun under one code identity", "after all case-1 results existed: sessions, macro "
                                                                   "and recheck rerun under code f1a6d625064a6d18; "
                                                                   "old runs archived; chains kept"),
            ("5", "shared GPU lock", "a lock defect let processes overlap; numbers unaffected (replays exact), but "
                                     "timings before about 09:40 are inflated by contention")]
    vt = read_text(v6n)
    for k, head, _ in devs:
        assert re.search(rf"^{k}\. \*\*2026-11-08, {re.escape(head)}", vt, re.M | re.I), (k, head)
    a3_thr, floor_db = a3_thr.replace("-", "−"), floor_db.replace("-", "−")   # typographic minus
    L.add("T7", "v6.deviations", len(devs), v6n, "numbered items of section 7 'Deviations'", status="derived",
          script=S)
    notes = [
        f"Source: the session, macro, chain and recheck JSON files of `results/verification/v6/`; every number is "
        f"formatted from them at full precision (`{src}`, written from the same files by "
        "scripts/verify/v6/build_t7.py with rounding, agrees after rounding). Acceptance thresholds were specified "
        "before solver runs; targets were selected using the atlas, and the logged procedural amendments were applied "
        "(V6 NOTES sections 1-3 and 7).",
        "Acceptance (V6 NOTES 8.3): A1 certification, A2 macro stiffness, A3 6-cell transmission (design − reference "
        f"≤ {a3_thr} dB, both drives, both meshes), A4 reference validity, A5 exported-geometry recheck, F1/F5 for the "
        "filter: all PASS.",
        "Procedural amendments logged during V6 (V6 NOTES section 7): " +
        "; ".join(f"({k}) {head}, {what}" for k, head, what in devs) + ".",
        "Flags (reported, not verdicts): " + "; ".join(flags) + ". The PA12 filter fails manufacturing screening: "
        f"min solid {float(pa['min_solid_mm']):.2f} mm < {float(pa['printer_limit_mm']):.1f} mm SLS limit. "
        "Screening is not a printability claim.",
        f"Chain: 6 cells along [001], periodic in x and y (normal incidence only), hysteretic η = {eta:g}, rigid bonded "
        f"input plate, free output face. In-band levels below about {floor_db} dB have no practical meaning beyond "
        f"strongly attenuated; only the {a3_thr} dB comparison is claimed.",
        "Mount stiffness: homogenized block with the guarded C* (lower E100, lower G, worst ν100); requirement 7.2 "
        "kN/mm (0.25 mm under 1.8 kN). Axial load only; no shear, buckling, creep or strength check.",
        "Times: case-2 and first case-1 timings were inflated by contention with V2 (V6 NOTES deviation 5); "
        "the case-1 rows are the rerun under code f1a6d625064a6d18.",
        _released_note(L),
    ]
    return write_table("T7_engineering_cases", "Engineering cases (V6): requirements, certified designs, margins, "
                       "flags and checks", ["Item", "Mount: design", "Mount: reference", "Filter: PA12",
                                            "Filter: 316L"], rows, notes,
                       colspec="p{3.6cm}p{3.1cm}p{3.1cm}p{3.1cm}p{3.1cm}", label="tab:cases")


# ============================================================================================================ T1
RW_CSV = "research/related_work.csv"
RW_PY = "scripts/paper/make_related_work_xlsx.py"


def _rw_t1():
    """T1 codes and feature names from make_related_work_xlsx.py, read with ast (that script needs openpyxl, which
    the amm env does not have, so it is not imported)."""
    tree = ast.parse(read_text(RW_PY))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("FEATURES", "T1") and isinstance(node.value, ast.Call):
                out[name] = ast.literal_eval(node.value.args[0])
            elif name == "THIS_WORK":
                out[name] = ast.literal_eval(node.value)
    return out


def _evidence_by_tag(text, tags):
    out = {}
    t = "|".join(tags)
    for m in re.finditer(r"(?:^|;\s*)(%s|STIFF\+GAP):\s*(.*?)(?=;\s*(?:%s|STIFF\+GAP):|$)" % (t, t), text or ""):
        out[m.group(1)] = m.group(2).strip()
    return out


T1_INSPECT = "scripts/paper/t1_inspection_2026-11-08.csv"   # follow-up inspection of '?' and evidence-less cells


def t1_features(L: Ledger):
    d = _rw_t1()
    feats = d["FEATURES"]
    tags = [k for k, _ in feats]
    by_id = {r["id"]: r for r in read_csv(RW_CSV)}
    insp = {(r["tool"], r["tag"]): r for r in read_csv(T1_INSPECT)}
    names = {n for n, _ in d["T1"]}
    assert all(t in names and g in tags and r["code"] in ("Y", "P", "N", "U") and r["url"].startswith("https://")
               and r["read_on"] for (t, g), r in insp.items()), "bad row in " + T1_INSPECT
    rows, ev_lines, n_q, n_noev, n_u = [], [], 0, 0, 0
    qcells, noev_cells, ucells, resolved = [], [], [], []
    for name, (ids, codes) in d["T1"]:
        codes = codes.split()
        ev = {}
        for i in ids.split("+"):
            for k, v in _evidence_by_tag(by_id[i]["evidence"], tags).items():
                ev[k] = (ev[k] + " | " if k in ev else "") + f"[{i}] {v}"
        cells = []
        ev_lines += [f"### {name} [{ids}]", ""]
        for j, ((tag, fname), code) in enumerate(zip(feats, codes)):
            e = ev.get(tag)
            ins = insp.get((name, tag))
            if ins:
                old = code
                code = ins["code"]
                e = (e + " | " if e else "") + f"[inspected {ins['read_on']}] {ins['evidence']} (source: {ins['url']}, " \
                                               f"read {ins['read_on']})"
                if code == "U":
                    ucells.append(f"{name}: {fname}")
                else:
                    resolved.append(f"{name}: {fname} {old} -> {code}" if old != code else
                                    f"{name}: {fname} {code} (evidence added)")
            if code == "U":
                cell = "unknown"
                n_u += 1
            elif code == "?":
                cell = "? (unverified)"
                n_q += 1
                qcells.append(f"{name}: {fname}")
            elif e is None:
                cell = f"{code} (no evidence)"
                n_noev += 1
                noev_cells.append(f"{name}: {fname}")
            else:
                cell = code
            cells.append(cell)
            ev_lines.append(f"- {fname}: **{'unknown' if code == 'U' else code}** - " + (e or "no evidence entry in the `evidence` column"))
            L.add("T1", f"{name}.{tag}", cell, f"{RW_PY}; {RW_CSV}" + (f"; {T1_INSPECT}" if ins else ""),
                  f"T1['{name}'] code; evidence column of {ids}" + (f"; inspection row ({ins['url']}, read "
                                                                    f"{ins['read_on']})" if ins else "")
                  + ("" if e else " (none recorded)"), script=S)
        ev_lines.append("")
        rows.append([name, ids] + cells)
    # this work: from the V2 matrix and the V6/B6 records (the draft row in related_work is a plan, not evidence)
    mat = read_csv(f"{V2}/matrix.csv")

    def row(scen, check, iface):
        hit = [r for r in mat if r["scenario"] == scen and r["check"] == check and r["interface"] == iface]
        assert hit and hit[0]["result"] in ("pass", "refused as expected"), (scen, check, iface)
        return f"{V2}/matrix.csv {scen}/{check} ({iface}): {hit[0]['result']}"

    tw = {
        "OS": ("pending", "BSD-3-Clause (LICENSE), confirmed by the author 2026-11-08; not yet published (repository after the paper is "
                          "finalized)"),
        "GUI": ("Y", row("X_edge", "edge_proven_infeasible", "gui-edge") + "; live GUI clicks in headless Edge"),
        "STIFF": ("Y", row("S11_certified_static", "pa12_certify", "gui") + "; certified E100 target in MPa"),
        "GAP3D": ("Y", row("S13_lib_combined", "combo_certify", "lib") + "; certified stiffness + complete gap"),
        "THERM": ("N", "thermal module B8 cut for this paper (plan, mid-point review dispositions)"),
        "VERIF": ("Y", "certificate blocks and thresholds: table T3; verification V1: table T4"),
        "BOUNDS": ("Y", row("S16_addendum", "proven_infeasible_r2", "lib") + "; refusal citing a bound record"),
        "AGENT": ("Y", row("S11_certified_static", "pa12_certify", "mcp") + "; MCP server driven by a client"),
        "STL": ("Y", row("S11_certified_static", "pa12_export", "mcp") + "; single cell + tiled STL and report"),
    }
    tw_cells = []
    ev_lines += ["### This work (amm 0.2.0)", ""]
    for tag, fname in feats:
        code, e = tw[tag]
        assert e, f"T1 this-work {tag}: no V2 row found"
        tw_cells.append(code)
        ev_lines.append(f"- {fname}: **{code}** - {e}")
        src_tw = (e.split(" ")[0] if e.startswith("results/") else
                  "LICENSE (licence decision: the author, 2026-11-08, relayed by the coordinator)" if tag == "OS" else
                  "plan (mid-point review dispositions)" if tag == "THERM" else "tables T3, T4")
        L.add("T1", f"this_work.{tag}", code, src_tw, e, script=S)
    rows.append(["This work (amm 0.2.0)", "-"] + tw_cells)
    draft = d["THIS_WORK"][1].split()
    changed = [f"{fn}: draft {a} -> {b}" for (tag, fn), a, b in zip(feats, draft, tw_cells) if a != b]
    L.add("T1", "n_unverified_cells", n_q, f"{RW_PY}; {T1_INSPECT}", "count of '?' codes left in T1",
          status="derived", script=S)
    L.add("T1", "n_cells_without_evidence", n_noev, f"{RW_PY}; {RW_CSV}; {T1_INSPECT}",
          "non-'?' codes with no evidence tag in the entry", status="derived", script=S)
    L.add("T1", "n_unknown_cells", n_u, T1_INSPECT, "cells inspected on the read date and still not documented (U)",
          status="derived", script=S)
    L.add("T1", "n_resolved_cells", len(resolved), T1_INSPECT, "cells given a documented code by the inspection",
          status="derived", script=S)
    L.add("T1", "n_tools", len(d["T1"]), RW_PY, "len(T1)", status="derived", script=S)
    notes = [
        "Codes (research/related_work.md section 2): Y offered (seen in the inspected repository or docs); P partial "
        "or a building block; N not offered according to the inspected docs (read as 'not documented in the inspected "
        "version'); unknown: not documented in the inspected version (sources read on the date given), which is not "
        "evidence of absence.",
        f"Every cell cites the evidence text of the entry in `{RW_CSV}` (column `evidence`, tag per feature) and, for "
        f"the cells inspected again, the row of `{T1_INSPECT}` with its source URL and read date; the full text per "
        "cell is in `paper/tables/T1_evidence.md`. Codes are from `" + RW_PY + "` (T1), updated by that file.",
        f"Follow-up inspection ({len(insp)} cells, public docs and repositories, read only): resolved "
        f"{len(resolved)}: " + "; ".join(resolved) + f". Still unknown ({n_u}): " + "; ".join(ucells) + ".",
    ]
    if n_q:
        notes.append(f"Unverified: {n_q} cells are '?' and must be checked before submission: " + "; ".join(qcells)
                     + ".")
    if n_noev:
        notes.append(f"No evidence recorded: {n_noev} cells have a code but no evidence entry: "
                     + "; ".join(noev_cells) + ".")
    notes += [
        "This-work row: filled from the V2 acceptance matrix (T12) and the release notes, not from the plan draft. "
        "Changes from the draft row: " + ("; ".join(changed) if changed else "none") + ".",
    ]
    hdr = ["Tool", "Entry"] + [fn for _, fn in feats]
    p = write_table("T1_feature_comparison", "Feature comparison with existing tools (inspected documentation)",
                    hdr, rows, notes, colspec="p{2.6cm}l" + "p{1.05cm}" * len(feats), label="tab:features")
    ev_md = ["# T1 evidence per cell", "",
             f"Generated by `scripts/paper/make_all.py` (T1) from `{RW_CSV}` (column `evidence`) and the codes in "
             f"`{RW_PY}`, updated by `{T1_INSPECT}` (source URL and read date per inspected cell). One line per cell: "
             "feature, code, evidence. 'unknown' = not documented in the inspected version (not evidence of absence); "
             "'?' = not inspected.", ""] + ev_lines
    pe = ROOT / "paper/tables/T1_evidence.md"
    pe.write_text("\n".join(ev_md) + "\n", encoding="utf-8")
    return p + [pe]


# ============================================================================================================ T10
def t10_prior(L: Ledger):
    rows_csv = [r for r in read_csv(RW_CSV) if r["category"] == "f"]
    # what this paper credits to each entry and does not claim: plan section 2, "Explicitly not claimed"
    plan_noncl = {
        "F01": "verify-before-release / refuse-with-evidence principle; catalogue retrieval and stiffness-"
               "conductivity combinations",
        "F02": "verify-before-release / refuse-with-evidence principle",
        "F03": "verify-before-release / refuse-with-evidence principle",
        "F04": "clarification of incomplete specifications",
        "F05": "agent-tool-certificate-GUI-replay architecture; latency/KLM evaluation style",
        "F06": "none (different topic: LLM control of SIMP continuation); overlap note for AES",
        "F07": "none listed in the plan; earlier GUI + LLM topology-optimization work, cited",
    }
    rows = []
    for r in rows_csv:
        ident = r["arxiv"] and f"arXiv {r['arxiv']}" or ""
        if r["doi"]:
            ident = (ident + "; " if ident else "") + f"doi {r['doi']}"
        rows.append([f"{r['id']} {r['first_author']} {r['year']}", ident, r["venue"], r["what_it_does"],
                     f"{r['licence']}", plan_noncl.get(r["id"], "-")])
        for k in ("arxiv", "doi", "venue", "licence"):
            if r[k]:
                L.add("T10", f"{r['id']}.{k}", r[k], RW_CSV, f"{k} of {r['id']}", script=S)
    L.add("T10", "n_entries", len(rows_csv), RW_CSV, "rows with category f", status="derived", script=S)
    notes = [
        f"Source: `{RW_CSV}`, category (f), {len(rows_csv)} entries (identifiers checked on arXiv/Crossref on "
        "2026-11-07; venue status of preprints from the project notes, not checked here). 'What it does' is the "
        "`what_it_does` column (from abstracts; F04 from the title only).",
        "'Credited, not claimed here' follows plan section 2 ('Explicitly not claimed'); it states what this paper "
        "does not claim, not a judgement of those papers.",
        "What this paper adds (its own claims, not claims about the papers above): open software for periodic 3D "
        "cells with coupled stiffness and complete-gap targets in physical units (S1); tiered numerical acceptance "
        "with five outcomes and refusal evidence (S2); a held-out search benchmark (S3, no clear advantage of BO); "
        "engineering workflows with acceptance tests (S4); the E4 bundle result on the frozen implementation (S5).",
        "Mid-point review: T10 covers the two prior papers added to the log (F06 AES 2026, F07 AutoSiMP) next to "
        "the original five.",
    ]
    return write_table("T10_prior_work", "Delta to the author's prior work",
                       ["Entry", "Identifier", "Venue / status", "What it does", "Licence", "Credited, not claimed here"],
                       rows, notes, colspec="p{2.0cm}p{2.4cm}p{2.2cm}p{4.6cm}lp{3.4cm}", label="tab:prior")


# ============================================================================================================ T14
def t14_install(L: Ledger):
    b6, b9, v2n = "results/software/NOTES_B6.md", "results/software/NOTES_B9.md", f"{V2}/NOTES.md"
    ci = ".github/workflows/ci.yml"
    rows = []
    rows.append("## Clean installs of the wheel (CPU only)")
    w_t = grab(L, "T14", "win.install_time", b6, r'\[all\]"`: \*\*(\d+ s), success\*\*', unit="s")
    w_py = grab(L, "T14", "win.python", b6, r"venv: Anaconda base (Python [\d.]+)")
    w_tests = grab(L, "T14", "win.tests", b6, r"final conftest: \*\*(\d+ passed, \d+ skipped \(data\), \d+ deselected "
                                              r"\(gpu\), \d+ failed)\*\* in (\d+ s)")
    w_ts = grab(L, "T14", "win.tests_time", b6, r"final conftest: \*\*[^*]+\*\* in (\d+ s)", unit="s")
    w_whl = grab(L, "T14", "win.wheel", b6, r"Wheel `(amm-0\.2\.0-py3-none-any\.whl)` \(([\d,]+ B)")
    rows.append(["Windows 11, clean venv", f"{w_py}, torch 2.15.0+cpu", f"pip install {w_whl}[all]: {w_t}",
                 f"pytest -m \"not gpu\": {w_tests}, {w_ts}", "B6 code 5970bf55108f1584"])
    l_py = grab(L, "T14", "linux.platform", b6, r"Platform: (Debian 13 \(trixie\), Python [\d.]+)")
    l_ins = grab(L, "T14", "linux.install", b6, r"then the wheel `\[all\]` and\s+`pytest>=9\.0` from PyPI, (\d+ s)",
                 unit="s")
    l_t = grab(L, "T14", "linux.tests", b6, r'Tests, `-m "not gpu"`: \*\*(\d+ passed, \d+ skipped \(data\), \d+ '
                                            r'deselected \(gpu\), \d+ failed)\*\* in (\d+ s)')
    l_ts = grab(L, "T14", "linux.tests_time", b6, r'Tests, `-m "not gpu"`: \*\*[^*]+\*\* in (\d+ s)', unit="s")
    rows.append(["Linux container python:3.12-slim (WSL2, no GPU)", l_py, f"torch CPU index, then wheel[all]: {l_ins}",
                 f"pytest -m \"not gpu\": {l_t}, {l_ts}", "B6 code 5970bf55108f1584"])
    b9w = grab(L, "T14", "b9.wheel_install", b9, r"installed \(core only, ([\d.]+ min)\)", unit="min")
    rows.append(["Windows, clean venv after B9", "Python 3.11.5, core extras only",
                 f"pip install wheel (core): {b9w}", "smoke run outside the checkout (atlas via AMM_DATA_DIR); "
                 "no test suite", "B9 code 5ab7480410467482"])
    b7 = "results/software/b7/T14_b7.csv"
    with open(ROOT / b7, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            p = r["platform"]
            res = f"{r['passed']} passed, {r['skipped']} skipped, {r['deselected']} deselected, {r['failed']} failed"
            L.add("T14", f"b7.{p}.tests", res, b7, f"row {p}: passed/skipped/deselected/failed", script=S)
            L.add("T14", f"b7.{p}.code", r["code_hash"], b7, f"row {p}: code_hash", script=S)
            L.add("T14", f"b7.{p}.checker", r["checker_hash"], b7, f"row {p}: checker_hash", script=S)
            env = "Windows 11, clean venv (B7 release wheel)" if p == "windows" else \
                "Linux container python:3.12-slim (WSL2, no GPU; B7 release wheel)"
            rows.append([env, f"Python {r['python']}, torch {r['torch']}",
                         f"release wheel sha256 {r['wheel_sha256'][:12]}..., data bundle verified: {r['data_verify_ok']}",
                         f"pytest -m \"not gpu\": {res}, {float(r['seconds']):.0f} s",
                         f"{r['code_hash']} / checker {r['checker_hash']}"])
    rows.append("## Full test suite in the project environment (RTX 4090, solver lock held)")
    for lab, log, code in (("after B1-B3", "results/software/b1b3_full_tests.log", "B3 (hash not in the log)"),
                           ("after B9", "results/software/b9/b9_full_tests.log", "5ab7480410467482"),
                           ("after V2 (incl. new CLI tests)", f"{V2}/logs/full_tests.log", "f1a6d625064a6d18")):
        s = _pytest_summary(log)
        L.add("T14", f"suite.{lab}", s, log, "last pytest summary line", script=S)
        rows.append([f"Project env, {lab}", "Python 3.10.18, CUDA", "editable checkout", s, code])
    b6s = grab(L, "T14", "suite.after_B6", b6, r"\*\*(151 passed, 0 skipped, 0 failed)\*\* in (\d+ s)")
    rows.insert(-2, ["Project env, after B6", "Python 3.10.18, CUDA", "editable checkout", f"{b6s} (log outside the "
                     "repository; NOTES_B6 section 6)", "5970bf55108f1584"])
    rerun = _pytest_summary(f"{V2}/logs/live_test_rerun.log")
    L.add("T14", "suite.v2_skip_rerun", rerun, f"{V2}/logs/live_test_rerun.log", "pytest summary", script=S)
    # CI
    y = read_text(ci)
    oss = re.search(r"os: \[([^\]]+)\]", y).group(1)
    pys = re.search(r"python: \[([^\]]+)\]", y).group(1).replace('"', "")
    steps = re.findall(r"- name: (.+)", y)
    to = re.search(r"timeout-minutes: (\d+)", y).group(1)
    L.add("T14", "ci.os", oss, ci, "strategy.matrix.os", script=S)
    L.add("T14", "ci.python", pys, ci, "strategy.matrix.python", script=S)
    L.add("T14", "ci.steps", len(steps), ci, "named steps", status="derived", script=S)
    L.add("T14", "ci.timeout_min", to, ci, "timeout-minutes", script=S)
    rows.append("## Continuous integration (written, not yet run)")
    rows.append([f"GitHub Actions `{ci}`", f"{oss}; Python {pys}", "CPU torch index, then .[test]",
                 "; ".join(steps), "never run: no remote"])
    tests_v2 = grab(L, "T14", "tests.total_v2", v2n, r"Full test suite under the lock: (\d+) passed, (\d+) skipped")
    m = re.search(r"Full test suite under the lock: (\d+) passed, (\d+) skipped", read_text(v2n))
    total = int(m.group(1)) + int(m.group(2))
    L.add("T14", "tests.total_after_v2", total, v2n, "passed + skipped of the V2 full suite", status="derived",
          script=S)
    notes = [
        "Sources: results/software/NOTES_B6.md (clean installs, sections 3 and 3b; B6 suite, section 6), "
        "results/software/NOTES_B9.md (B9 wheel and suite), the pytest logs named in the rows, "
        f"`{V2}/NOTES.md` section 5, and `{ci}`.",
        f"Test count after V2: {total} tests ({m.group(1)} passed, {m.group(2)} skipped because another process held "
        f"the solver lock; that test passed when rerun alone: {rerun}).",
        "The B6 clean-install runs (90 passed) used code 5970bf55108f1584. B7 repeated the clean installs with the "
        "release wheel of the current code (f1a6d625064a6d18) on Windows and Linux (results/software/NOTES_B7.md, "
        "b7/T14_b7.csv); a first B7 run had one failure on both platforms (a repo-only test without its skip "
        "marker; conftest fixed, no assertion changed; logs in b7/run1/).",
        "Missing: a run of the CI workflow (no remote exists), native Linux (only a WSL2 container), macOS (not "
        "supported: PARDISO/MKL) and the Zenodo data DOI. The licence (BSD-3-Clause code, CC-BY-4.0 data) is "
        "confirmed by the author 2026-11-08. The GUI (app/, web/) is not in the wheel; it runs from a "
        "source checkout.",
        "The Windows clean install used PIP_CONFIG_FILE=nul because the machine's pip configuration adds an "
        "unreachable extra index (a machine setting, not a packaging problem; NOTES_B6 section 3).",
    ]
    return write_table("T14_install_ci", "Installation and continuous integration (V9 part done so far)",
                       ["Environment", "Platform", "Install", "Result", "Code identity"], rows, notes,
                       colspec="p{3.2cm}p{2.8cm}p{3.4cm}p{4.6cm}p{2.4cm}", label="tab:install")


# ============================================================================================================ T15
def t15_reproducibility(L: Ledger):
    """Hook for V10 (another work package writes results/verification/v10/T15_v10.csv). Builds the table only if
    that file exists; otherwise returns nothing and the README lists T15 as waiting for V10."""
    p = ROOT / T15_SRC
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        rows_csv = list(csv.DictReader(f))
    if not rows_csv:
        return []
    hdr = list(rows_csv[0].keys())
    rows = []
    for i, r in enumerate(rows_csv):
        rows.append([r[h] for h in hdr])
        for h in hdr[1:]:
            if r[h] not in ("", None):
                L.add("T15", f"{r[hdr[0]]}.{h}", r[h], T15_SRC, h, script=S)
    notes = [f"Source: `{T15_SRC}` (V10), copied column by column; see results/verification/v10/NOTES.md for the "
             "replay sets, identities and tolerances."]
    return write_table("T15_reproducibility", "Reproducibility: replay sets (V10)", hdr, rows, notes,
                       label="tab:replay")


ALL = [t1_features, t7_cases, t10_prior, t12_matrix, t14_install, t15_reproducibility]
