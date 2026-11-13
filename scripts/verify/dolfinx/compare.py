"""V1c host side: compare amm certificates with the DOLFINx bands by the pre-registered rule
(results/verification/dolfinx/NOTES.md, "V1c protocol"). Reads only stored JSON (no solves).

    python scripts/verify/dolfinx/compare.py            -> results/verification/dolfinx/<case>.json, summary.csv,
                                                          fig_<case>.png, fig_summary.png
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / "results/verification/dolfinx"
INP, RAW, AMM = D / "inputs", D / "raw", D / "amm"
ORDER = ["cb_c0.6_w0.2_nu0.342", "cb_c0.8_w0.3_nu0.3", "cb_c0.5_w0.2_nu0.3", "cb_c0.6_w0.3_nu0.3",
         "cb_c0.7_w0.3_nu0.3", "tpms_schwarzp_d0.25_nu0.3", "strut_bcc_R0.27_r0.06_nu0.342",
         "thin_sl_c0.402_w0.061_nu0.3"]


def load(p):
    return json.load(open(p)) if Path(p).exists() else None


def kin(k, ks):
    return any(np.allclose(k, q, atol=1e-9) for q in ks)


def edges(recs, nb, ks=None):
    rr = [r for r in recs if ks is None or kin(r["k"], ks)]
    if not rr:
        return None, None, None, None
    lo = max(rr, key=lambda r: r["f"][nb - 1])
    hi = min(rr, key=lambda r: r["f"][nb])
    return lo["f"][nb - 1], hi["f"][nb], lo["k"], hi["k"]


def extrapolate(h, E):
    """Protocol: order fit through three levels (p clipped to [0.5, 4]) if monotone with shrinking steps."""
    from scipy.optimize import brentq
    d12, d23 = E[1] - E[0], E[2] - E[1]
    if d12 != 0 and d23 != 0 and d12 * d23 > 0 and abs(d23) < abs(d12):
        g = lambda p: (h[1] ** p - h[2] ** p) / (h[0] ** p - h[1] ** p) - d23 / d12
        try:
            p = brentq(g, 0.05, 12.0)
        except ValueError:
            p = None
        pu = None if p is None else float(np.clip(p, 0.5, 4.0))
        if pu is not None:
            r = h[2] ** pu / (h[1] ** pu - h[2] ** pu)
            return dict(mode="order-fit", p=p, p_used=pu, ext=E[2] + d23 * r,
                        u=max(abs(d23) * r, 1e-4 * abs(E[2])), seq=E, h=h)
    return dict(mode="non-monotone", p=None, p_used=None, ext=E[2], u=max(abs(d12), abs(d23), 1e-4 * abs(E[2])),
                seq=E, h=h)


def classify_lo(s, ext, u):
    return "sound" if s >= ext + 2 * u else ("marginal" if s >= ext - 2 * u else "unsound")


def classify_hi(s, ext, u):
    return "sound" if s <= ext - 2 * u else ("marginal" if s <= ext + 2 * u else "unsound")


def identity(case, nb):
    dfx = load(RAW / case / "q1id_n20.json")
    am = load(AMM / f"{case}_id_n20_ks_id.json")
    if not dfx or not am:
        return None
    worst, strict, rigid, rows = 0.0, 0.0, 0.0, []
    for r in dfx["records"]:
        a = next((q for q in am["records"] if np.allclose(q["k"], r["k"], atol=1e-9)), None)
        if a is None:
            continue
        fd, fa = np.array(r["f"][: nb + 4]), np.array(a["f"][: nb + 4])
        err_all = np.abs(fd - fa) / np.maximum(fa, 0.01)
        nz = np.abs(np.array(a["lam"][: nb + 4])) > 1e-9  # rigid-body modes at Gamma (deviation 4 in NOTES.md)
        err = err_all[nz] if nz.any() else np.zeros(1)
        strict = max(strict, float(err_all.max()))
        rigid = max(rigid, float(np.abs(fd[~nz]).max(initial=0.0)), float(np.abs(fa[~nz]).max(initial=0.0)))
        rows.append(dict(k_over_pi=(np.array(r["k"]) / np.pi).round(4).tolist(), max_rel=float(err.max()),
                         res_dfx=float(np.max(np.array(r["rel_res"][: nb + 4])[nz])) if nz.any() else 0.0,
                         res_amm=float(np.max(np.array(a["rel_res"][: nb + 4])[nz])) if nz.any() else 0.0))
        worst = max(worst, float(err.max()))
    ok = bool(rows) and worst <= 1e-6  # frequency criterion; residuals reported separately (deviation 7)
    res_ok = all(r["res_dfx"] <= 1e-8 and r["res_amm"] <= 1e-8 for r in rows)
    res_max = dict(dfx=max(r["res_dfx"] for r in rows), amm=max(r["res_amm"] for r in rows)) if rows else None
    return dict(n=20, k_points=len(rows), max_rel_diff=worst, passed=ok, rows=rows,
                strict_letter_max_rel_incl_rigid=strict, rigid_mode_max_f=rigid, residuals_le_1e8=res_ok,
                residual_max=res_max,
                ndof_dfx=dfx["records"][0]["ndof"], ndof_amm=am["ndof"])


def analyse(case):
    c = json.load(open(INP / f"{case}.json"))
    nb = c["below_band"]
    exact = c["geometry"] is not None
    lv = [10, 15, 20] if exact else [16, 20, 30]
    n4 = 30 if exact else 40
    L = {n: load(RAW / case / f"q2_n{n}.json") for n in lv + [n4]}
    if any(L[n] is None for n in lv):
        return None
    S_amm = c["ks"]["path"] + c["ks"]["interior"] + c["ks"]["adversarial"]
    S_dfx = load(RAW / case / "ks_dfx.json") or []

    def reference(levels, hdef="nominal"):
        ks = [r["k"] for r in L[levels[-1]]["records"]]  # the finest level's k-set
        # h = 1/n (deviation 9: the breakpoint-aligned grids are slightly non-uniform and their largest cell edge
        # jumps with rounding, e.g. 0.125, 0.10, 0.05 for c 0.8 w 0.3, which made a fitted order of 6.4)
        h = [1.0 / n if hdef == "nominal" else L[n]["mesh"]["h_max"] for n in levels]
        E = {n: edges(L[n]["records"], nb, ks) for n in levels}
        return (extrapolate(h, [E[n][0] for n in levels]), extrapolate(h, [E[n][1] for n in levels]), E, h)

    # protocol: the three finest levels on the finest level's k-set (with l4 present: lv[1], lv[2], n4 at the two
    # edge k); the coarse three-level version (lv) is reported alongside
    used = [lv[1], lv[2], n4] if L[n4] is not None else lv
    ref_lo, ref_hi, E, h = reference(used)
    c_lo3, c_hi3, _, _ = reference(lv)
    hm_lo, hm_hi, _, _ = reference(used, "hmax")
    s_lo, s_hi = c["amm"]["safe_interval"]
    f_lo, f_hi = c["claim"]
    v_lo = classify_lo(s_lo, ref_lo["ext"], ref_lo["u"])
    v_hi = classify_hi(s_hi, ref_hi["ext"], ref_hi["u"])
    fin_lo, fin_hi = E[used[-1]][0], E[used[-1]][1]
    alln = [n for n in lv + [n4] if L[n] is not None]
    out = dict(case=case, role=c["role"], spec=c["spec"], nu=nu_of(c), below_band=nb, model="exact" if exact else "fcm",
               levels=alln, levels_reference=used, h_reference=h, claim=c["claim"], amm_safe=[s_lo, s_hi],
               amm_edges=c["amm"]["edges"], amm_phase_edges=c["amm"]["phase_edges"],
               dolfinx_edges={str(n): dict(lo=edges(L[n]["records"], nb)[0], hi=edges(L[n]["records"], nb)[1],
                                           k_lo_over_pi=(np.array(edges(L[n]["records"], nb)[2]) / np.pi).round(4).tolist(),
                                           k_hi_over_pi=(np.array(edges(L[n]["records"], nb)[3]) / np.pi).round(4).tolist(),
                                           ndof=max(r["ndof"] for r in L[n]["records"]), n_k=len(L[n]["records"]),
                                           h_max=L[n]["mesh"]["h_max"])
                              for n in alln},
               ref_lo=ref_lo, ref_hi=ref_hi, verdict_lo=v_lo, verdict_hi=v_hi,
               hmax_reference=dict(ref_lo=hm_lo, ref_hi=hm_hi, verdict_lo=classify_lo(s_lo, hm_lo["ext"], hm_lo["u"]),
                                   verdict_hi=classify_hi(s_hi, hm_hi["ext"], hm_hi["u"])),
               coarse_reference=dict(levels=lv, ref_lo=c_lo3, ref_hi=c_hi3,
                                     verdict_lo=classify_lo(s_lo, c_lo3["ext"], c_lo3["u"]),
                                     verdict_hi=classify_hi(s_hi, c_hi3["ext"], c_hi3["u"])))
    # supplementary (not the pre-registered rule): extrapolate each k separately, then take the extreme over k;
    # the protocol's edge-sequence fit is distorted when the extreme k changes between levels
    pk = {}
    ks_ref = [r["k"] for r in L[used[-1]]["records"]]
    for side, band, pick in (("lo", nb - 1, max), ("hi", nb, min)):
        exts = []
        for k in ks_ref:
            seq = [next(q["f"][band] for q in L[n]["records"] if np.allclose(q["k"], k, atol=1e-9)) for n in used]
            e = extrapolate(h, seq)
            exts.append((e["ext"], e["u"], (np.array(k) / np.pi).round(4).tolist(), e["p"]))
        best = pick(exts, key=lambda t: t[0])
        pk[side] = dict(ext=best[0], u=best[1], k_over_pi=best[2], p=best[3])
    pk["verdict_lo"] = classify_lo(s_lo, pk["lo"]["ext"], pk["lo"]["u"])
    pk["verdict_hi"] = classify_hi(s_hi, pk["hi"]["ext"], pk["hi"]["u"])
    out["per_k_reference"] = pk
    # per-k tightest DOLFINx value (minimum over levels): on exact cells an upper bound of the continuum band
    ub = {}
    for n in alln:
        for r in L[n]["records"]:
            key = tuple(np.round(r["k"], 9))
            lo_v, hi_v = r["f"][nb - 1], r["f"][nb]
            o = ub.get(key, (np.inf, np.inf))
            ub[key] = (min(o[0], lo_v), min(o[1], hi_v))
    ub_lo = max(v[0] for v in ub.values())
    ub_hi = min(v[1] for v in ub.values())
    out["upper_bounds_over_sampled_k"] = dict(lo=ub_lo, hi=ub_hi, n_k=len(ub))
    if exact:  # Rayleigh-Ritz on the exact geometry
        out["rigorous_lo_sound_at_sampled_k"] = bool(s_lo >= ub_lo)
        out["rigorous_hi_unsound"] = bool(s_hi > ub_hi)
    out["claim_inside_reference"] = bool(f_lo >= ref_lo["ext"] + 2 * ref_lo["u"] and f_hi <= ref_hi["ext"] - 2 * ref_hi["u"])
    out["claim_inside_finest_gap"] = bool(f_lo > fin_lo and f_hi < fin_hi)
    gw = ref_hi["ext"] - ref_lo["ext"]
    out["conservatism"] = dict(c_lo=s_lo - ref_lo["ext"], c_hi=ref_hi["ext"] - s_hi,
                               gap_ref=gw, gap_not_certified=1 - (s_hi - s_lo) / gw if gw > 0 else None,
                               margin_over_2u_lo=(s_lo - ref_lo["ext"]) / (2 * ref_lo["u"]),
                               margin_over_2u_hi=(ref_hi["ext"] - s_hi) / (2 * ref_hi["u"]))
    # raw amm edges vs reference (descriptive)
    out["amm_raw_vs_ref"] = {n: dict(lo_rel=(v[0] - ref_lo["ext"]) / ref_lo["ext"], hi_rel=(v[1] - ref_hi["ext"]) / ref_hi["ext"])
                             for n, v in c["amm"]["edges"].items()}
    # k coverage at the levels that evaluated S_amm and S_dfx
    cov = {}
    for n in lv[:2]:
        ea = edges(L[n]["records"], nb, S_amm)
        ed = edges(L[n]["records"], nb, None)
        cov[str(n)] = dict(lo_Samm=ea[0], lo_all=ed[0], hi_Samm=ea[1], hi_all=ed[1],
                           d_lo=ed[0] - ea[0], d_hi=ea[1] - ed[1],
                           k_lo_all_over_pi=(np.array(ed[2]) / np.pi).round(4).tolist(),
                           k_hi_all_over_pi=(np.array(ed[3]) / np.pi).round(4).tolist())
    srch = load(RAW / case / "search.json")
    if srch:
        cov["search_n10"] = dict(dense_edges=srch["dense_edges"], best_lo=srch["search"]["lo"]["best"],
                                 best_hi=srch["search"]["hi"]["best"],
                                 k_lo_over_pi=(np.array(srch["search"]["lo"]["best_k"]) / np.pi).round(4).tolist(),
                                 k_hi_over_pi=(np.array(srch["search"]["hi"]["best_k"]) / np.pi).round(4).tolist(),
                                 n_solves=len(srch["records"]))
    # amm's own certificate model at DOLFINx's k
    am_cov = {}
    for n in (20, 30):
        a = load(AMM / f"{case}_cert_n{n}_ks_dfx.json")
        if a:
            lo = max(r["f"][nb - 1] for r in a["records"])
            hi = min(r["f"][nb] for r in a["records"])
            ce = c["amm"]["edges"][str(n)]
            am_cov[str(n)] = dict(lo_at_Sdfx=lo, hi_at_Sdfx=hi, cert_lo=ce[0], cert_hi=ce[1],
                                  beyond_lo=max(0.0, lo - ce[0]), beyond_hi=max(0.0, ce[1] - hi),
                                  # 1e-12 relative: on TPMS s_lo equals amm's raw n = 20 edge, which the rerun
                                  # reproduces to 1.7e-15 (round-off, not a more extreme k)
                                  beyond_safe=bool(lo > s_lo * (1 + 1e-12) or hi < s_hi * (1 - 1e-12)))
    out["k_coverage"] = cov
    out["amm_model_at_dolfinx_k"] = am_cov
    out["k_beyond_safe"] = bool(any(v["lo_all"] > s_lo or v["hi_all"] < s_hi for k, v in cov.items() if k != "search_n10")
                                or any(v["beyond_safe"] for v in am_cov.values()))
    out["identity"] = identity(case, nb)
    sl = load(RAW / case / f"q2_n{lv[1]}_slepc.json")
    if sl:
        worst = 0.0
        for r in sl["records"]:
            b = next((q for q in L[lv[1]]["records"] if np.allclose(q["k"], r["k"], atol=1e-9)), None)
            lam = np.array(r["lam"][: nb + 4])
            e = np.abs(np.array(r["f"][: nb + 4]) - np.array(b["f"][: nb + 4])) / np.maximum(np.array(b["f"][: nb + 4]), 0.01)
            worst = max(worst, float(e[np.abs(lam) > 1e-9].max()))
        out["solver_crosscheck"] = dict(level=lv[1], k_points=len(sl["records"]), max_rel_diff=worst,
                                        note="SLEPc subspace (shift-invert, MUMPS) on dolfinx_mpc.assemble_matrix vs block "
                                             "Krylov on the serial fast path")
    out["dolfinx_seconds"] = load(RAW / case / "timing.json")
    out["max_rel_res_edge_bands"] = max(max(r["rel_res"][nb - 1], r["rel_res"][nb]) for n in lv for r in L[n]["records"])
    out["max_rel_res"] = max(max(np.array(r["rel_res"])[np.abs(np.array(r["lam"])) > 1e-9].max(initial=0)
                                 for r in L[n]["records"]) for n in lv)
    return out


def nu_of(c):
    return c["nu"]


def figure(res, c, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    nb = res["below_band"]
    lv = res["levels"]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw=dict(width_ratios=[3, 1.4]), sharey=True)
    path_ks = c["ks"]["path"]
    cols = dict(zip(lv, ["#c6dbef", "#6baed6", "#2171b5", "#08306b"]))
    for n in lv:
        recs = load(RAW / res["case"] / f"q2_n{n}.json")["records"]
        xs, lo, hi = [], [], []
        for i, k in enumerate(path_ks):
            r = next((q for q in recs if np.allclose(q["k"], k, atol=1e-9)), None)
            if r:
                xs.append(i), lo.append(r["f"][nb - 1]), hi.append(r["f"][nb])
        mk = "-o" if len(xs) == len(path_ks) else "o"
        ax.plot(xs, lo, mk, ms=3, color=cols[n], label=f"DOLFINx Q2 n={n}: bands {nb}, {nb + 1}")
        ax.plot(xs, hi, mk, ms=3, color=cols[n])
        other = [q for q in recs if not kin(q["k"], path_ks)]
        bx.plot([0.15 + 0.1 * lv.index(n)] * len(other), [q["f"][nb - 1] for q in other], "v", ms=3, color=cols[n])
        bx.plot([0.15 + 0.1 * lv.index(n)] * len(other), [q["f"][nb] for q in other], "^", ms=3, color=cols[n])
    s_lo, s_hi = res["amm_safe"]
    for a in (ax, bx):
        a.axhspan(s_lo, s_hi, color="#a1d99b", alpha=0.35, lw=0)
        a.axhspan(*res["claim"], color="#31a354", alpha=0.25, lw=0)
        for side in ("ref_lo", "ref_hi"):
            r = res[side]
            a.axhspan(r["ext"] - 2 * r["u"], r["ext"] + 2 * r["u"], color="#de2d26", alpha=0.25, lw=0)
            a.axhline(r["ext"], color="#de2d26", lw=1)
        for n, (lo, hi) in res["amm_edges"].items():
            a.axhline(lo, color="#636363", lw=0.8, ls=(0, (3, 2)))
            a.axhline(hi, color="#636363", lw=0.8, ls=(0, (3, 2)))
    ticks = [0, 4, 8, 12, 16, 20]
    ax.set_xticks(ticks, ["Γ", "X", "M", "Γ", "R", "X"])
    ax.set_xlim(-0.5, 20.5)
    bx.set_xticks([0.3], ["interior, adversarial\nand DOLFINx-search k"])
    bx.set_xlim(0, 0.6)
    ax.set_ylabel("f* = f a / c_t")
    ax.set_title(f"{res['case']}  (gap above band {nb})", fontsize=10)
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    h = ax.get_legend_handles_labels()[0] + [
        Patch(color="#a1d99b", alpha=0.6, label="amm certified safe interval"),
        Patch(color="#31a354", alpha=0.5, label="claim"),
        Patch(color="#de2d26", alpha=0.4, label="DOLFINx extrapolated edge ± 2u"),
        Line2D([], [], color="#636363", ls=(0, (3, 2)), label="amm certificate edges n=20/30/40")]
    lo_all = min(min(v["lo"] for v in res["dolfinx_edges"].values()), s_lo) - 0.08
    hi_all = max(max(v["hi"] for v in res["dolfinx_edges"].values()), s_hi) + 0.08
    ax.set_ylim(lo_all - 0.15, hi_all + 0.1)
    ax.legend(handles=h, fontsize=6.5, loc="lower right", ncol=2, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def summary_figure(rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4))
    for i, r in enumerate(rows):
        lo, hi = r["ref_lo"], r["ref_hi"]
        ax.plot([i, i], [lo["ext"], hi["ext"]], color="#de2d26", lw=8, alpha=0.25, solid_capstyle="butt")
        for e in (lo, hi):
            ax.errorbar(i, e["ext"], yerr=2 * e["u"], color="#de2d26", capsize=3, lw=1)
        ax.plot([i + 0.18, i + 0.18], r["amm_safe"], color="#31a354", lw=4)
        ax.plot([i + 0.3, i + 0.3], r["claim"], color="#006d2c", lw=2)
    ax.set_xticks(range(len(rows)), [r["case"].replace("_nu", "\nnu").replace("_r0", "\nr0").replace("_w0.061", "\nw0.061")
                                     for r in rows], fontsize=6.5)
    ax.set_ylabel("f*")
    ax.set_title("Gap: DOLFINx reference (red, ±2u) vs amm safe interval (green) and claim (dark green)", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    rows = []
    for case in ORDER:
        r = analyse(case)
        if r is None:
            print("incomplete:", case)
            continue
        json.dump(r, open(D / f"{case}.json", "w"), indent=1, default=float)
        figure(r, json.load(open(INP / f"{case}.json")), D / f"fig_{case}.png")
        rows.append(r)
    if not rows:
        return
    keys = ["case", "role", "model", "below_band", "claim_lo", "claim_hi", "amm_safe_lo", "amm_safe_hi",
            "dfx_finest_lo", "dfx_finest_hi", "ref_lo", "u_lo", "ref_hi", "u_hi", "p_lo", "p_hi", "verdict_lo",
            "verdict_hi", "rigorous_lo_sound", "rigorous_hi_unsound", "claim_inside_ref", "c_lo", "c_hi",
            "gap_not_certified", "k_beyond_safe", "identity_max_rel", "identity_passed", "amm_n40_lo_rel",
            "amm_n40_hi_rel"]
    with open(D / "summary.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(keys)
        for r in rows:
            lv = r["levels_reference"]
            idt = r["identity"] or {}
            w.writerow([r["case"], r["role"], r["model"], r["below_band"], *r["claim"], *r["amm_safe"],
                        r["dolfinx_edges"][str(lv[2])]["lo"], r["dolfinx_edges"][str(lv[2])]["hi"],
                        r["ref_lo"]["ext"], r["ref_lo"]["u"], r["ref_hi"]["ext"], r["ref_hi"]["u"],
                        r["ref_lo"]["p"], r["ref_hi"]["p"], r["verdict_lo"], r["verdict_hi"],
                        r.get("rigorous_lo_sound_at_sampled_k", ""), r.get("rigorous_hi_unsound", ""),
                        r["claim_inside_reference"], r["conservatism"]["c_lo"], r["conservatism"]["c_hi"],
                        r["conservatism"]["gap_not_certified"], r["k_beyond_safe"], idt.get("max_rel_diff", ""),
                        idt.get("passed", ""), r["amm_raw_vs_ref"]["40"]["lo_rel"], r["amm_raw_vs_ref"]["40"]["hi_rel"]])
    summary_figure(rows, D / "fig_summary.png")
    for r in rows:
        print(f"{r['case']:32s} lo {r['verdict_lo']:8s} hi {r['verdict_hi']:8s} safe {np.round(r['amm_safe'], 4)} "
              f"ref [{r['ref_lo']['ext']:.4f}±{2 * r['ref_lo']['u']:.4f}, {r['ref_hi']['ext']:.4f}±{2 * r['ref_hi']['u']:.4f}] "
              f"claim_in {r['claim_inside_reference']} id {(r['identity'] or {}).get('max_rel_diff')}")


if __name__ == "__main__" and "--md" not in __import__("sys").argv:
    main()


def markdown():
    """Results table for NOTES.md (python compare.py --md)."""
    rows = []
    for case in ORDER:
        p = D / f"{case}.json"
        if p.exists():
            rows.append(json.load(open(p)))
    print("| Case | nb | claim | amm safe interval | DOLFINx finest [lo, hi] (n) | reference lo ± 2u | reference hi ± 2u | "
          "verdict lo / hi | gap not certified | identity max rel |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        n = str(r["levels_reference"][-1])
        e = r["dolfinx_edges"][n]
        print(f"| {r['case']} | {r['below_band']} | {r['claim'][0]:.4f}–{r['claim'][1]:.4f} | "
              f"{r['amm_safe'][0]:.4f}–{r['amm_safe'][1]:.4f} | {e['lo']:.4f}, {e['hi']:.4f} ({n}) | "
              f"{r['ref_lo']['ext']:.4f} ± {2 * r['ref_lo']['u']:.4f} | {r['ref_hi']['ext']:.4f} ± {2 * r['ref_hi']['u']:.4f} | "
              f"{r['verdict_lo']} / {r['verdict_hi']} | {100 * r['conservatism']['gap_not_certified']:.0f} % | "
              f"{(r['identity'] or {}).get('max_rel_diff', float('nan')):.1e} |")


if __name__ == "__main__" and "--md" in __import__("sys").argv:
    markdown()
