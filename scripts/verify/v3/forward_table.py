"""V3 forward-solver comparison against the external tool, from existing V1 files only (nothing rerun).

Reads results/verification/dolfinx/ (V1c, DOLFINx 0.11 + dolfinx_mpc, third-party) and results/verification/v1b/
(own Q2-FCM + scikit-fem, semi-independent). Writes results/verification/v3/forward_vs_dolfinx.md.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DFX = ROOT / "results" / "verification" / "dolfinx"
V1B = ROOT / "results" / "verification" / "v1b"
OUT = ROOT / "results" / "verification" / "v3" / "forward_vs_dolfinx.md"
SRC = {  # source certificate of each V1c case (results/verification/dolfinx/NOTES.md, protocol table)
    "cb_c0.6_w0.2_nu0.342": ROOT / "results/verification/indep/cube_bars_c0.6_w0.2_nu0.342_amm.json",
    "cb_c0.8_w0.3_nu0.3": ROOT / "results/verification/indep/cube_bars_c0.8_w0.3_nu0.3_amm.json",
    "cb_c0.5_w0.2_nu0.3": ROOT / "results/verification/indep/cube_bars_c0.5_w0.2_nu0.3_g2_amm.json",
    "cb_c0.6_w0.3_nu0.3": ROOT / "results/verification/indep/cube_bars_c0.6_w0.3_nu0.3_g2_amm.json",
    "cb_c0.7_w0.3_nu0.3": ROOT / "results/verification/indep/cube_bars_c0.7_w0.3_nu0.3_g2_amm.json",
    "tpms_schwarzp_d0.25_nu0.3": DFX / "amm/tpms_schwarzp_d0.25_nu0.3_bloch.json",
    "strut_bcc_R0.27_r0.06_nu0.342": ROOT / "results/bench/e4/jobs/codex-C-r1-A15/session/certificates/"
                                            "feceec63a345ee84_8306e070463fa197.json",
    "thin_sl_c0.402_w0.061_nu0.3": ROOT / "results/bench/e4/jobs/codex-C-r1-G10/session/certificates/"
                                          "40d98d0c519c50a5_f8934f3a9d393e14.json",
}


def j(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def f(x, n=4):
    return "" if x is None or x == "" else f"{float(x):.{n}g}"


def main():
    rows = list(csv.DictReader(open(DFX / "summary.csv", encoding="utf-8")))
    L = ["# Forward-solver comparison: amm against DOLFINx-MPC (V1c) and the V1b two-sided checks",
         "",
         "Built by `scripts/verify/v3/forward_table.py` from existing files only (`results/verification/dolfinx/`,",
         "`results/verification/v1b/`); nothing was rerun. Protocols, deviations and caveats: the NOTES.md of each",
         "folder. DOLFINx 0.11.0 + dolfinx_mpc 0.11.0 (complex PETSc, MUMPS, 8 MPI ranks in a container) is the",
         "third-party code; V1b's Q2-FCM is the author's own second code and scikit-fem 12.0.2 shares its geometry",
         "evaluator (semi-independent).",
         "",
         "## A. Bloch band edges (8 cells, 16 edges; third party)",
         "",
         "Accuracy. ref = DOLFINx extrapolated edge +- 2u (three finest levels). amm safe = the certificate's",
         "guarded edge. c = amm's margin (safe edge inside the reference gap; positive = conservative). raw n40 =",
         "amm's finest raw edge relative to the reference (positive = above). Identity = largest relative frequency",
         "difference between DOLFINx Q1 midpoint-rule and amm's same discrete model (n = 20, 6 k, bands 1..nb+4).",
         "",
         "| Case | model | ref lo +- 2u | amm safe lo | c_lo (/2u) | ref hi +- 2u | amm safe hi | c_hi (/2u) | verdict lo/hi | raw n40 lo/hi | identity |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        c = r["case"]
        ulo, uhi = float(r["u_lo"]), float(r["u_hi"])
        L.append(f"| {c} | {r['model']} | {f(r['ref_lo'])} +- {f(2 * ulo, 2)} | {f(r['amm_safe_lo'])} | "
                 f"{f(r['c_lo'], 3)} ({float(r['c_lo']) / (2 * ulo):.1f}) | {f(r['ref_hi'])} +- {f(2 * uhi, 2)} | "
                 f"{f(r['amm_safe_hi'])} | {f(r['c_hi'], 3)} ({float(r['c_hi']) / (2 * uhi):.1f}) | "
                 f"{r['verdict_lo']} / {r['verdict_hi']} | {100 * float(r['amm_n40_lo_rel']):+.1f} % / "
                 f"{100 * float(r['amm_n40_hi_rel']):+.1f} % | {float(r['identity_max_rel']):.1e} |")
    n_sound = sum((r["verdict_lo"] == "sound") + (r["verdict_hi"] == "sound") for r in rows)
    n_marg = sum((r["verdict_lo"] == "marginal") + (r["verdict_hi"] == "marginal") for r in rows)
    n_uns = sum((r["verdict_lo"] == "unsound") + (r["verdict_hi"] == "unsound") for r in rows)
    L += ["", f"Edges: {n_sound} sound, {n_marg} marginal, {n_uns} unsound (of {2 * len(rows)}).", ""]

    L += ["Runtime. DOLFINx: Q2 at n = 20 (8 ranks; seconds for the level's k-set and per k), and the Q1 identity",
          "model (6 k). amm: the same identity model (6 k; host-side block subspace iteration of the V1c harness, CPU,",
          "not amm's production eigen path), amm's certificate model at DOLFINx's k (n = 20, CPU), and the wall time",
          "of the whole certificate Bloch block (n = 20, 30, edge level 40, 2 grid phases, adversarial k search;",
          "GPU + CPU) from the source certificate.",
          "",
          "| Case | DOLFINx Q2 n20: dof, k, s (s/k) | DOLFINx Q1-id n20: dof, s / 6 k | amm id n20: dof, s / 6 k | amm cert model n20 at S_dfx: dof, k, s | amm certificate Bloch block s | DOLFINx k search s |",
          "|---|---|---|---|---|---|---|"]
    tot = dict(dq2=0.0, did=0.0, aid=0.0, acert=0.0, ablk=0.0, dsearch=0.0)
    for r in rows:
        c = r["case"]
        q2 = j(DFX / "raw" / c / "q2_n20.json") if (DFX / "raw" / c / "q2_n20.json").exists() else None
        qid = j(DFX / "raw" / c / "q1id_n20.json")
        aid = j(DFX / "amm" / f"{c}_id_n20_ks_id.json")
        acp = DFX / "amm" / f"{c}_cert_n20_ks_dfx.json"
        ac = j(acp) if acp.exists() else None
        src = j(SRC[c])
        blk = (src.get("timing") or {}).get("bloch")
        ds = j(DFX / f"{c}.json")["dolfinx_seconds"]
        q2s = (f"{q2['records'][0]['ndof']}, {len(q2['records'])}, {q2['seconds']:.0f} ({q2['seconds'] / len(q2['records']):.1f})"
               if q2 else "n/a")
        L.append(f"| {c} | {q2s} | {qid['records'][0]['ndof']}, {qid['seconds']:.1f} | {aid['ndof']}, {aid['seconds']:.1f} | "
                 + (f"{ac['ndof']}, {len(ac['records'])}, {ac['seconds']:.0f}" if ac else "n/a")
                 + f" | {f(blk, 4)} | {ds.get('search', float('nan')):.0f} |")
        tot["dq2"] += q2["seconds"] if q2 else 0
        tot["did"] += qid["seconds"]
        tot["aid"] += aid["seconds"]
        tot["acert"] += ac["seconds"] if ac else 0
        tot["ablk"] += blk or 0
        tot["dsearch"] += ds.get("search", 0)
    L += ["", f"Sums over the 8 cells: DOLFINx Q2 n20 {tot['dq2']:.0f} s, DOLFINx Q1-id {tot['did']:.0f} s, amm id "
              f"{tot['aid']:.0f} s, amm cert model at S_dfx {tot['acert']:.0f} s, amm certificate Bloch blocks "
              f"{tot['ablk']:.0f} s, DOLFINx k searches {tot['dsearch']:.0f} s. V1c totals (its NOTES.md): DOLFINx about "
              "5.7 h of container compute (8 cores), amm side about 3.6 h.", "",
          "Reading the runtime columns: the DOLFINx and amm timings are not a like-for-like speed test. DOLFINx runs",
          "Q2 (about 7x the unknowns of amm's hex8i at the same n) on 8 MPI ranks; the amm identity timing uses the V1c",
          "harness's eigen solver; amm's production paths are the GPU dense search tier (about 1 s per cell for static",
          "+ bands, V3 runs.csv) and the certificate's inertia-count Lanczos. The table states what each run cost, not",
          "a speed ratio of the two codes.", ""]

    # ---- V1b static (semi-independent) ----
    t = list(csv.DictReader(open(V1B / "T4_v1b.csv", encoding="utf-8")))
    st = [x for x in t if x["check"].startswith("static:") and x["check"] != "static:density"]
    L += ["## B. Homogenized stiffness (V1b; own Q2-FCM reference and scikit-fem, semi-independent)", "",
          "delta = amm's extrapolated estimate relative to the Q2-FCM reference; bounds = soundness of amm's guarded",
          "lower / upper bound against the reference +- 2u; scikit-fem = its n = 16 value relative to the reference.",
          "", "| Cell | quantity | ref | amm est. | delta | lower / upper | scikit-fem delta |", "|---|---|---|---|---|---|---|"]
    for x in st:
        L.append(f"| {x['cell']} | {x['check'].split(':')[1]} | {f(x['ref'])} | {f(x['amm_estimate'])} | "
                 f"{100 * float(x['delta_rel']):+.2f} % | {x['status_lower']} / {x['status_upper']} | "
                 + (f"{100 * float(x['skfem_delta']):+.2f} %" if x["skfem_delta"] else "") + " |")
    sb = [x["status_lower"] for x in st] + [x["status_upper"] for x in st]
    L += ["", f"Static bounds: {sb.count('sound')} sound, {sb.count('marginal')} marginal, {sb.count('unsound')} "
              f"unsound (of {len(sb)}); |delta| median "
              f"{100 * sorted(abs(float(x['delta_rel'])) for x in st)[len(st) // 2]:.2f} %, max "
              f"{100 * max(abs(float(x['delta_rel'])) for x in st):.2f} %. V1b compute: 8.4 solver-hours "
              "(its NOTES.md).", ""]
    OUT.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
