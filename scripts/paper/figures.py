"""Data figures F3, F4, F5, F6, F10, F11 (plan item A1), drawn with matplotlib from result files only.

Each function declares the result files it plots (`fn.sources`); make_all.py refuses a figure without sources, which
keeps diagrams (F1 and the like) out of this folder. Style: scripts/paper/style.py (8 pt at print width).
"""
from __future__ import annotations

import collections
import glob
import json
import statistics as stt
from pathlib import Path

import numpy as np

import style
from common import FIGURES, ROOT, Ledger, fnum, pct, read_csv, read_json, read_jsonl
from style import DOUBLE, FAMILY, METHOD, MM, OKABE, OUTCOME, SINGLE, panel_label

S = "scripts/paper/figures.py"
plt = None


def _plt():
    global plt
    style.apply()
    import matplotlib.pyplot as p
    plt = p
    return p


def sources(*files):
    def deco(fn):
        fn.sources = list(files)
        return fn
    return deco


_READER = {"check_bounds": "bounds check", "atlas_suggest": "atlas suggestion", "screen_manufacturing": "screening",
           "cube_bars": "cube and bars", "sphere_ligaments": "sphere and ligaments", "as_built": "surface offset",
           "get_session": "session", "set_target": "set target", "set_material": "set material",
           "set_constraints": "set constraints", "set_source": "set source", "atlas_verdict": "atlas verdict"}


def _reader(name: str) -> str:
    """Reader words for a tool or geometry identifier shown in a figure."""
    return _READER.get(name, name.replace("_", " "))


def _short(cell: str) -> str:
    rep = {"tpms_schwarzp_sheet_d0.2895": "P sheet φ 0.29", "tpms_schwarzp_d0.25": "P network φ 0.25",
           "strut_bcc_R0.27_r0.06": "bcc r 0.06", "strut_octet_r0.06": "octet r 0.06",
           "thin_sl_c0.402_w0.061": "SL c 0.40 w 0.06", "thin_sl_c0.357_w0.109": "SL c 0.36 w 0.11"}
    base = cell.split("_nu")[0]
    if base in rep:
        return rep[base]
    if base.startswith("cb_"):
        p = base.split("_")
        return f"CB c {p[1][1:]} w {p[2][1:]}"
    return base


# ============================================================================================================ F3
@sources("results/verification/registry_rows.csv", "results/verification/v1b/T4_v1b.csv",
         "results/verification/indep/summary.json", "results/verification/skfem/summary.json",
         "results/g2/alignment_study.log", "results/g2/phase_study_cube.log")
def f3_stiffness(L: Ledger):
    _plt()
    fig = plt.figure(figsize=(DOUBLE, 150 * MM))
    gs = fig.add_gridspec(2, 2, width_ratios=[1, 1.75], height_ratios=[1.1, 1], hspace=0.75, wspace=0.3)

    # (a) registry parity
    ax = fig.add_subplot(gs[0, 0])
    rsrc = "results/verification/registry_rows.csv"
    rr = [r for r in read_csv(rsrc) if r["load_bearing"] == "True"]
    ok = [r for r in rr if float(r["rel_err"]) <= 1e-8]
    bad = [r for r in rr if float(r["rel_err"]) > 1e-8]
    mx = max(float(r["rel_err"]) for r in ok)
    ax.loglog([float(r["C_norm_cat"]) for r in ok], [float(r["C_norm_ours"]) for r in ok], "o", ms=2.2,
              mfc="none", mec=OKABE["blue"], mew=0.5, label=f"{len(ok)} rows, rel. diff. ≤ {mx:.2g}")
    ax.loglog([float(r["C_norm_cat"]) for r in bad], [float(r["C_norm_ours"]) for r in bad], "x", ms=4,
              color=OKABE["vermillion"], mew=0.9, label=f"{len(bad)} rows: stored density\n≠ rebuilt mask")
    lim = [min(float(r["C_norm_cat"]) for r in rr) * 0.6, max(float(r["C_norm_cat"]) for r in rr) * 1.6]
    ax.plot(lim, lim, "-", color=OKABE["grey"], lw=0.5, zorder=0)
    ax.set_xlim(lim), ax.set_ylim(lim)
    ax.set_xlabel(r"registry |C*| / E$_s$")
    ax.set_ylabel(r"AMM |C*| / E$_s$, same mask")
    ax.set_title("Registry catalogue rows", pad=4)
    ax.legend(loc="upper left", fontsize=8, handletextpad=0.2)
    panel_label(ax, "a", x=-0.24)
    L.add("F3", "a.series_agree", len(ok), rsrc, "load-bearing rows rel_err <= 1e-8", status="derived", script=S)
    L.add("F3", "a.series_bad", len(bad), rsrc, "load-bearing rows rel_err > 1e-8", status="derived", script=S)
    L.add("F3", "a.max_rel_err_agree", f"{mx:.2g}", rsrc, "max rel_err over agreeing rows", status="derived",
          script=S)

    # (b) V1b two-sided static deltas with amm guard interval and reference band
    ax = fig.add_subplot(gs[0, 1])
    vsrc = "results/verification/v1b/T4_v1b.csv"
    v = read_csv(vsrc)
    qs = ["E100", "G", "bulk"]
    cells = list(dict.fromkeys(r["cell"] for r in v))
    x, xt, xl = 0, [], []
    clip = 15.0
    clipped = []
    for ci, c in enumerate(cells):
        for qi, q in enumerate(qs):
            r = [r for r in v if r["cell"] == c and r["check"] == f"static:{q}"][0]
            R, u = float(r["ref"]), float(r["ref_u"])
            lo, hi, est = [100 * (float(r[k]) - R) / abs(R) for k in ("amm_lower", "amm_upper", "amm_estimate")]
            col = FAMILY[r["family"]]
            ax.add_patch(plt.Rectangle((x - 0.34, -200 * u / abs(R)), 0.68, 400 * u / abs(R),
                                       color=OKABE["lightgrey"], lw=0, zorder=1))
            ax.plot([x, x], [max(lo, -clip), min(hi, clip)], "-", color=col, lw=1.8, solid_capstyle="butt", zorder=2)
            if lo < -clip:
                ax.plot([x], [-clip], "v", ms=4, color=col, clip_on=False, zorder=4)
                ax.text(x + 0.22, -clip + 0.6, f"{lo:.0f}", ha="left", va="bottom", fontsize=8, color=col)
            if hi > clip:
                ax.plot([x], [clip], "^", ms=4, color=col, clip_on=False, zorder=4)
                ax.text(x + 0.22, clip - 0.6, f"{hi:+.0f}", ha="left", va="top", fontsize=8, color=col)
            if lo < -clip or hi > clip:
                clipped.append(f"{_short(c).split(chr(32) + chr(119))[0]} {q} [{lo:.0f}, {hi:+.0f}]")
            mk = {"E100": "o", "G": "s", "bulk": "D"}[q]
            ax.plot([x], [max(min(est, clip), -clip)], mk, ms=3.4, color="k", mfc="white", mew=0.7, zorder=3)
            xt.append(x)
            xl.append({"E100": "E", "G": "G", "bulk": "K"}[q])
            x += 1
        x += 1.2
    ax.axhline(0, color=OKABE["grey"], lw=0.5, zorder=0)
    ax.set_ylim(-clip, clip)
    ax.set_xlim(-0.8, x - 1.0)
    ax.set_xticks(xt)
    ax.set_xticklabels(xl, fontsize=8)
    ax.set_ylabel("difference from reference (%)")
    centers = [np.mean(xt[i * 3:(i + 1) * 3]) for i in range(len(cells))]
    two = {"P network φ 0.25": "P network\nφ 0.25", "P sheet φ 0.29": "P sheet\nφ 0.29",
           "bcc r 0.06": "bcc\nr 0.06", "octet r 0.06": "octet\nr 0.06", "SL c 0.40 w 0.06": "SL c 0.40\nw 0.06",
           "SL c 0.36 w 0.11": "SL c 0.36\nw 0.11"}
    for cx, c in zip(centers, cells):
        ax.text(cx, -0.13, two.get(_short(c), _short(c)), transform=ax.get_xaxis_transform(), ha="center",
                va="top", fontsize=8)
    ax.set_title("Quadratic finite-cell comparison (two-sided)", pad=4)
    from matplotlib.patches import Patch
    hd = [Patch(color=OKABE["lightgrey"], label="reference ± 2u"),
          plt.Line2D([], [], color=FAMILY["tpms"], lw=1.8, label="AMM guarded interval: TPMS"),
          plt.Line2D([], [], color=FAMILY["struts"], lw=1.8, label="struts"),
          plt.Line2D([], [], color=FAMILY["resonator"], lw=1.8, label="resonators"),
          plt.Line2D([], [], marker="o", ls="", color="k", mfc="white", label="AMM estimate (E, G, K)")]
    ax.legend(handles=hd, loc="upper center", bbox_to_anchor=(0.5, -0.33), ncol=3, fontsize=8)
    panel_label(ax, "b", x=-0.08)
    L.add("F3", "b.series", 3 * len(cells), vsrc, "static E100/G/bulk rows: amm_lower/upper/estimate vs ref, ref_u",
          status="derived", script=S)
    for t in clipped:
        L.add("F3", "b.clipped", t, vsrc, "(amm_lower - ref)/ref, (amm_upper - ref)/ref in %", status="derived",
              script=S)

    # (c) one-sided: amm guarded lower / independent upper bound
    ax = fig.add_subplot(gs[1, 0])
    isrc, ssrc = "results/verification/indep/summary.json", "results/verification/skfem/summary.json"
    ind, sk = read_json(isrc), read_json(ssrc)
    groups = collections.OrderedDict([("Q2 FE\nn = 20", []), ("Q2 FE\nn = 40", []), ("scikit-fem\nKUBC", [])])
    for r in ind["rows"]:
        for n, vv in r["indep"].items():
            for q, s in vv["static"].items():
                if "necessary_check_passed" in s:
                    groups[f"Q2 FE\nn = {n[1:]}"].append(s["amm_lower"] / s["indep_upper_bound"])
    for r in sk["rows"]:
        for q, s in r["static"].items():
            groups["scikit-fem\nKUBC"].append(s["amm_lower"] / s["skfem_kubc_upper_bound"])
    rng = np.random.default_rng(0)
    for i, (k, vals) in enumerate(groups.items()):
        xs = i + rng.uniform(-0.2, 0.2, len(vals))
        ax.plot(xs, vals, "o", ms=2.4, mfc="none", mec=OKABE["blue"], mew=0.5)
        L.add("F3", f"c.{k.replace(chr(10), ' ')}.pass", f"{sum(x <= 1 for x in vals)}/{len(vals)}",
              isrc if "Q2" in k else ssrc, "count amm_lower / independent upper bound <= 1", status="derived",
              script=S)
    ax.axhline(1, color=OKABE["vermillion"], lw=0.7, ls="--")
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([k + "\n" + f"{sum(x <= 1 for x in v_)}/{len(v_)} ≤ 1" for k, v_ in groups.items()],
                       fontsize=8)
    ax.set_ylim(0, 1.08)
    ax.set_xlim(-0.5, len(groups) - 0.5)
    ax.set_ylabel("AMM guarded lower / upper bound")
    ax.set_title(f"One-sided checks, {len(ind['rows'])} cases", pad=4)
    panel_label(ax, "c", x=-0.3)

    # (d) grid phase: why the static guard solves several grid phases
    ax = fig.add_subplot(gs[1, 1])
    asrc, psrc = "results/g2/alignment_study.log", "results/g2/phase_study_cube.log"
    al = read_jsonl(asrc)
    c_, w_ = 0.7, 0.2   # alignment_study.log is the cube_bars c 0.7, w 0.2 study (results/g2/NOTES.md section 3)
    faces = [(1 - c_) / 2, (1 - w_) / 2]

    def aligned(n):
        return all(abs(f * n - round(f * n)) < 1e-9 for f in faces)
    A = [(r["n"], r["G"]) for r in al if aligned(r["n"])]
    C = [(r["n"], r["G"]) for r in al if not aligned(r["n"])]
    ax.plot([1 / n for n, _ in A], [1e3 * gg for _, gg in A], "o-", color=OKABE["blue"], ms=3,
            label="cell faces on voxel faces")
    ax.plot([1 / n for n, _ in C], [1e3 * gg for _, gg in C], "s-", color=OKABE["orange"], ms=3,
            label="cell faces cut by voxels")
    ph = read_jsonl(psrc)
    gph = [r["G"] for r in ph if r["n"] == 64]
    ax.plot([1 / 64] * len(gph), [1e3 * x for x in gph], "_", ms=9, color=OKABE["vermillion"], mew=1.3,
            label=f"n = 64, {len(gph)} grid phases")
    spread = (max(gph) - min(gph)) / stt.mean(gph)
    ax.annotate(f"spread {100 * spread:.1f} %", (1 / 64, 1e3 * min(gph)), xytext=(0.026, 7.68),
                fontsize=8, color=OKABE["vermillion"], arrowprops=dict(arrowstyle="-", lw=0.5,
                                                                        color=OKABE["vermillion"]))
    ax.set_xlabel("h = 1/n")
    ax.set_ylabel(r"G / E$_s$ ($\times 10^{-3}$)")
    ax.set_xlim(0, max(1 / n for n, _ in A + C) * 1.05)
    ax.set_title("Cut-voxel bias, cube-and-bars c 0.7, w 0.2", pad=4)
    ax.legend(loc="upper left", fontsize=8)
    panel_label(ax, "d", x=-0.08)
    L.add("F3", "d.series_aligned", len(A), asrc, "rows with c/w faces on voxel faces (computed from n)",
          status="derived", script=S)
    L.add("F3", "d.series_cut", len(C), asrc, "other rows", status="derived", script=S)
    L.add("F3", "d.phase_spread", pct(spread, 1, False), psrc, "(max - min)/mean of G at n = 64 over shifts",
          status="derived", script=S)
    return style.save(fig, "F3_stiffness_verification", FIGURES)


# ============================================================================================================ F4
@sources("results/verification/lucklum2018_ball079_beam005.json", "results/verification/v14/gaps.json")
def f4_bandgap(L: Ledger):
    _plt()
    from matplotlib.patches import Patch
    fig = plt.figure(figsize=(DOUBLE, 165 * MM))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 2.25], width_ratios=[2.1, 1], hspace=0.32, wspace=0.1)

    # (a) published gap
    ax = fig.add_subplot(gs[0, 0])
    lsrc = "results/verification/lucklum2018_ball079_beam005.json"
    lk = read_json(lsrc)
    p_lo, p_hi = lk[0]["paper"]["lo"], lk[0]["paper"]["hi"]
    ns = [r["n"] for r in lk]
    lo = [r["gaps_fa_over_cl"][0]["f_lo"] for r in lk]
    hi = [r["gaps_fa_over_cl"][0]["f_hi"] for r in lk]
    h = [1 / n for n in ns]
    rr = (1 / 60) / (1 / 40 - 1 / 60)
    elo, ehi = lo[-1] + (lo[-1] - lo[-2]) * rr, hi[-1] + (hi[-1] - hi[-2]) * rr
    ax.plot(h, [100 * (x / p_lo - 1) for x in lo], "o-", color=OKABE["blue"], label="lower edge")
    ax.plot(h, [100 * (x / p_hi - 1) for x in hi], "s-", color=OKABE["orange"], label="upper edge")
    ax.plot([0, h[-1]], [100 * (elo / p_lo - 1), 100 * (lo[-1] / p_lo - 1)], ":", color=OKABE["blue"])
    ax.plot([0, h[-1]], [100 * (ehi / p_hi - 1), 100 * (hi[-1] / p_hi - 1)], ":", color=OKABE["orange"])
    ax.plot([0], [100 * (elo / p_lo - 1)], "o", mfc="white", color=OKABE["blue"], label="O(h) extrapolation")
    ax.plot([0], [100 * (ehi / p_hi - 1)], "s", mfc="white", color=OKABE["orange"])
    ax.axhline(0, color=OKABE["grey"], lw=0.5)
    ax.set_xlim(-0.002, max(h) * 1.06)
    ax.set_xticks([0, 1 / 60, 1 / 40, 1 / 30, 1 / 20])
    ax.set_xticklabels(["0", "1/60", "1/40", "1/30", "1/20"])
    ax.set_xlabel("h = 1/n")
    ax.set_ylabel("deviation from\npublished edge (%)")
    ax.set_title("Published gap: Lucklum and Vellekoop (2018), ball 0.79a, beam 0.05a", pad=4)
    ax.legend(loc="upper left", fontsize=8)
    ax.text(0.03, 0.52, f"extrapolated (h → 0):\nlower {pct(elo / p_lo - 1, 1)},\nupper {pct(ehi / p_hi - 1, 1)}",
            transform=ax.transAxes, ha="left", va="top", fontsize=8)
    panel_label(ax, "a", x=-0.09)
    L.add("F4", "a.series", len(ns), lsrc, "edges at n = " + ",".join(map(str, ns)) + " / paper - 1", status="derived",
          script=S)
    L.add("F4", "a.extrapolated_dev", f"{pct(elo / p_lo - 1, 1)} / {pct(ehi / p_hi - 1, 1)}", lsrc,
          "O(h) extrapolation from n = 40, 60 relative to paper", status="derived", script=S)

    # legend and verdict box (text only) in the top right cell
    lx = fig.add_subplot(gs[0, 1])
    lx.axis("off")
    hd = [Patch(color=OKABE["lightgrey"], label="reference gap"),
          Patch(color=OKABE["grey"], alpha=0.55, label="reference edge ± 2u"),
          Patch(color=OKABE["blue"], label="AMM safe interval"),
          plt.Line2D([], [], color="k", lw=1.2, marker="|", label="certified claim"),
          plt.Line2D([], [], color=OKABE["grey"], lw=1.2, marker="|", label="claim not certified"),
          plt.Line2D([], [], marker="<", ls="", color=OKABE["green"], mec="k", mew=0.3, label="lower-edge margin"),
          plt.Line2D([], [], marker=">", ls="", color=OKABE["green"], mec="k", mew=0.3, label="upper-edge margin"),
          plt.Line2D([], [], marker="v", ls="", color=OKABE["orange"], mec="k", mew=0.3, label="marginal edge"),
          plt.Line2D([], [], marker="x", ls="", color=OKABE["vermillion"], mew=1.0, label="no safe edge")]
    lx.legend(handles=hd, loc="center left", fontsize=8, bbox_to_anchor=(0.04, 0.5), frameon=False)
    dsrc = "results/verification/dolfinx/summary.csv"

    # gather edges (V1b: Q2-FCM reference; V1c: DOLFINx reference), judged by the released edge guard
    # (results/verification/v14/gaps.json, scripts/experiments/v14_rule_rescore.py: an upper edge drifting toward the
    # claim with no admissible order has no safe value)
    gsrc = "results/verification/v14/gaps.json"
    rows = [dict(case=r["case"], src=r["src"], claim=r["claim"], safe=r["safe"], ref=r["ref"], u=r["u"],
                 st=tuple(r["status"]), certified=r["certified"])
            for r in read_json(gsrc)["figure_rows"]]
    N = len(rows)
    ylab = [_short(r['case']) for r in rows]  # comparison named in the panel title; ledger ids keep src
    nb = sum(r["src"] == "V1b" for r in rows)

    # (b) intervals
    ax = fig.add_subplot(gs[1, 0])
    for i, r in enumerate(rows):
        y = N - 1 - i
        (Rl, Rh), (ul, uh) = r["ref"], r["u"]
        ax.barh(y, Rh - Rl, left=Rl, height=0.72, color=OKABE["lightgrey"], lw=0, zorder=1)
        for e, uu in ((Rl, ul), (Rh, uh)):
            ax.barh(y, 4 * uu, left=e - 2 * uu, height=0.72, color=OKABE["grey"], alpha=0.55, lw=0, zorder=2)
        lo_s = r["safe"][0] if r["safe"][0] is not None else r["claim"][0]
        hi_s = r["safe"][1] if r["safe"][1] is not None else r["claim"][1]
        ax.barh(y, hi_s - lo_s, left=lo_s, height=0.34, color=OKABE["blue"] if r["safe"][1] is not None
                and r["safe"][0] is not None else "none", ec=OKABE["blue"], lw=0 if None not in r["safe"] else 0.8,
                ls="-" if None not in r["safe"] else (0, (2, 1.5)), zorder=3)
        ax.plot(r["claim"], [y, y], "-", color="k" if r["certified"] else OKABE["grey"], lw=1.2, zorder=4)
        ax.plot(r["claim"], [y, y], "|", color="k" if r["certified"] else OKABE["grey"], ms=5, mew=1.0, zorder=4)
        for j, s_ in enumerate(r["st"]):
            if s_ == "marginal":
                ax.plot([r["safe"][j]], [y + 0.5], "v", ms=4, color=OKABE["orange"], mec="k", mew=0.3, zorder=5)
            elif s_ == "no safe edge":
                ax.plot([r["claim"][j]], [y + 0.5], "x", ms=4.5, color=OKABE["vermillion"], mew=1.0, zorder=5)
    ax.axhline(N - nb - 0.5, color="k", lw=0.5)
    ax.set_yticks(range(N))
    ax.set_yticklabels(ylab[::-1], fontsize=8)
    ax.set_xlabel(r"normalized frequency f* = f a / c$_t$")
    ax.set_xlim(0, 1.0)
    ax.set_ylim(-0.6, N - 0.2)
    ax.set_title("Gap claims vs references (top: finite-cell; bottom: DOLFINx)", pad=4)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8])
    panel_label(ax, "b", x=-0.005)
    ev = collections.Counter(s for r in rows for s in r["st"])
    L.add("F4", "b.series", N, gsrc, "gap cases: claim, safe interval (released guard), reference ± 2u",
          status="derived", script=S)
    L.add("F4", "b.edge_status_counts", dict(ev), gsrc, "lo/hi statuses over all plotted cases (released guard)",
          status="derived", script=S)
    L.add("F4", "b.rows_certified", sum(r["certified"] for r in rows), gsrc,
          "plotted claims certified under the released rules (guard and feature resolution)", status="derived",
          script=S)

    # (c) margins in units of 2u, same rows
    bx = fig.add_subplot(gs[1, 1], sharey=ax)
    col = {"sound": OKABE["green"], "marginal": OKABE["orange"], "unsound": OKABE["vermillion"]}
    for i, r in enumerate(rows):
        mlo = None if r["safe"][0] is None else (r["safe"][0] - r["ref"][0]) / (2 * r["u"][0])
        mhi = None if r["safe"][1] is None else (r["ref"][1] - r["safe"][1]) / (2 * r["u"][1])
        y = N - 1 - i
        for m, s_, mk, dy in ((mlo, r["st"][0], "<", 0.15), (mhi, r["st"][1], ">", -0.15)):
            if m is None:
                bx.plot([0.12], [y + dy], "x", ms=4.5, color=OKABE["vermillion"], mew=1.0)
            else:
                bx.plot([max(m, 0.12)], [y + dy], mk, ms=4.5, color=col[s_], mec="k", mew=0.3)
        L.add("F4", f"c.margin.{r['src']}.{r['case']}",
              f"lo {'none' if mlo is None else f'{mlo:.2f}'}, hi {'none' if mhi is None else f'{mhi:.2f}'}", gsrc,
              "(safe - ref)/(2u) per edge; none: no safe edge", status="derived", script=S)
    bx.axhline(N - nb - 0.5, color="k", lw=0.5)
    bx.set_xscale("log")
    bx.axvline(1, color=OKABE["grey"], lw=0.6, ls="--")
    bx.axvspan(0.1, 1, color="#FFF4DD", lw=0, zorder=0)
    bx.text(0.13, N - 0.55, "marginal", fontsize=8, color=OKABE["orange"], va="top")
    bx.tick_params(axis="y", labelleft=False)
    bx.set_xlim(0.1, 150)
    bx.set_xlabel("safe-edge margin / 2u")
    bx.set_title("Margin (sound ≥ 1)", pad=4)
    panel_label(bx, "c", x=-0.04)
    return style.save(fig, "F4_bandgap_verification", FIGURES)


# ============================================================================================================ F5
@sources("results/verification/v14/bench/summary.json", "results/verification/v14/bench/runs.csv")
def f5_search(L: Ledger):
    _plt()
    ssrc, rsrc = "results/verification/v14/bench/summary.json", "results/verification/v14/bench/runs.csv"
    sm = read_json(ssrc)
    runs = [r for r in read_csv(rsrc) if r["set"] == "primary"]
    n = sm["n_primary_targets"]
    B = sm["budget"]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(DOUBLE, 72 * MM), gridspec_kw=dict(width_ratios=[1.25, 1],
                                                                                   wspace=0.32))
    names = sm["methods"]
    short = {"M1": "M1 atlas-only", "M2": "M2 Sobol", "M3": "M3 DE", "M4": "M4 BO (AMM)",
             "M5": "M5 BO, no seeding", "M6": "M6 BO, no correction"}
    end_x = {}
    for m, c in sm["curves"].items():
        y = c["nominal"]
        x = np.arange(len(y))
        ls = "--" if m == "M1" else "-"
        ax.step(x, y, where="post", color=METHOD[m], lw=1.1, ls=ls, label=short[m], zorder=4 if m == "M1" else 3)
        cert = sum(r["certified"] == "True" for r in runs if r["method"] == m) / n
        end_x[m] = cert
        L.add("F5", f"a.{m}.attain_final", y[-1], ssrc, f"curves.{m}.nominal[-1]", script=S)
        L.add("F5", f"a.{m}.certified_fraction", cert, rsrc, "certified / n (primary)", status="derived", script=S)
    # final certified endpoints at the right edge, offset per method to avoid overlap
    xs = {m: B + 2 + 1.3 * i for i, m in enumerate(sm["curves"])}
    for m in sm["curves"]:
        ax.plot([xs[m]], [end_x[m]], "D", ms=4, color=METHOD[m], mec="k", mew=0.3, clip_on=False, zorder=5)
    ax.axvspan(B + 0.8, B + 3 + 1.3 * len(xs), color="#F2F2F2", lw=0, zorder=0)
    ax.text(B + 2 + 1.3 * (len(xs) - 1) / 2, 0.02, "certified\n(final design)", ha="center", va="bottom", fontsize=8)
    ax.set_xlim(0, B + 3 + 1.3 * len(xs))
    ax.set_ylim(0, 1.0)
    ax.set_xticks([0, 8, 16, 24, 32, 40, 48])
    ax.set_xlabel("search-tier evaluations")
    ax.set_ylabel(f"fraction of {n} targets")
    ax.set_title("Search tier: selected candidate meets every target", pad=4)
    same = [m for m in sm["curves"] if m != "M1" and sm["curves"][m]["nominal"] == sm["curves"]["M1"]["nominal"]]
    if same:
        short["M1"] += f" (same curve as {', '.join(same)})"
        for t in ax.get_legend_handles_labels()[0]:
            if t.get_label().startswith("M1"):
                t.set_label(short["M1"])
        L.add("F5", "a.identical_curves", "M1 = " + ",".join(same), ssrc, "curves.*.nominal equal", status="derived",
              script=S)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=8)
    panel_label(ax, "a", x=-0.1)

    cats = [("certified", "certified"), ("undetermined", "undetermined"), ("refuted", "refuted"),
            ("not_certified_search_tier_miss", "search-tier miss (no certificate)")]
    ms = list(names)
    bottom = np.zeros(len(ms))
    for key, lab in cats:
        vals = np.array([sum(r["cert_verdict"] == key for r in runs if r["method"] == m) for m in ms])
        bx.bar(range(len(ms)), vals, bottom=bottom, color=OUTCOME[key], edgecolor="k", lw=0.4, width=0.7, label=lab)
        for i, v in enumerate(vals):
            if v:
                bx.text(i, bottom[i] + v / 2, str(v), ha="center", va="center", fontsize=8,
                        color="white" if key in ("certified", "refuted") else "k")
            L.add("F5", f"b.{ms[i]}.{key}", int(v), rsrc, f"count cert_verdict == {key}, primary", status="derived",
                  script=S)
        bottom += vals
    assert all(b == n for b in bottom), bottom
    bx.set_xticks(range(len(ms)))
    bx.set_xticklabels(ms)
    bx.set_ylabel(f"targets (of {n})")
    bx.set_ylim(0, n * 1.0)
    bx.set_yticks(range(0, n + 1, 5))
    bx.set_title("Final design per method: certificate outcome", pad=4)
    bx.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=8)
    panel_label(bx, "b", x=-0.12)
    return style.save(fig, "F5_search_benchmark", FIGURES)


# ============================================================================================================ F6
@sources("results/verification/v4/throughput.csv", "results/verification/v4/latency.csv",
         "results/verification/v4/cert_times.csv", "results/verification/v4/scaling.csv")
def f6_performance(L: Ledger):
    _plt()
    fig, axs = plt.subplots(2, 2, figsize=(DOUBLE, 125 * MM), gridspec_kw=dict(hspace=0.6, wspace=0.3))
    # (a) throughput vs batch
    ax = axs[0, 0]
    tsrc = "results/verification/v4/throughput.csv"
    th = [r for r in read_csv(tsrc) if r["mkl_threads"] == "16"]
    fcol = {"resonator": FAMILY["resonator"], "struts": FAMILY["struts"], "tpms": FAMILY["tpms"]}
    for fam in ("tpms", "struts", "resonator"):
        rr = sorted([r for r in th if r["family"] == fam], key=lambda r: int(r["batch"]))
        b = [int(r["batch"]) for r in rr]
        med = [float(r["warm_cells_per_s_median"]) for r in rr]
        lo = [float(r["warm_cells_per_s_min"]) for r in rr]
        hi = [float(r["warm_cells_per_s_max"]) for r in rr]
        ax.errorbar(b, med, yerr=[np.subtract(med, lo), np.subtract(hi, med)], fmt="o-", color=fcol[fam], ms=3,
                    capsize=2, lw=1, elinewidth=0.6, label=_reader(rr[0]["kind"]))
        ax.plot(b, [float(r["cold_cells_per_s"]) for r in rr], "x", color=fcol[fam], ms=4, mew=0.8)
        L.add("F6", f"a.{fam}.series", len(rr), tsrc, "warm median/min/max and cold cells/s at 16 threads",
              status="derived", script=S)
    ax.plot([], [], "x", color="k", ms=4, mew=0.8, label="cold start (first call)")
    ax.set_xscale("log", base=2)
    ax.set_xticks([1, 4, 16, 64])
    ax.set_xticklabels(["1", "4", "16", "64"])
    ax.set_xlim(0.7, 90)
    ax.set_ylim(0, 2.5)
    ax.set_xlabel("batch size (designs per call)")
    ax.set_ylabel("cells / s (search tier)")
    ax.set_title("Throughput, warm median and range", pad=4)
    ax.legend(loc="lower center", fontsize=8, ncol=2, columnspacing=0.8)
    panel_label(ax, "a", x=-0.14)

    # (b) tool latency (fresh); tool names are written next to the points to keep the panel narrow
    ax = axs[0, 1]
    lsrc = "results/verification/v4/latency.csv"
    lat = [r for r in read_csv(lsrc) if r["source"].startswith("V4 fresh") and float(r["median_s"]) > 0.01]
    lat.sort(key=lambda r: float(r["median_s"]))
    y = np.arange(len(lat))
    med = [float(r["median_s"]) for r in lat]
    lo = [float(r["min_s"]) for r in lat]
    hi = [float(r["max_s"]) for r in lat]
    ax.errorbar(med, y, xerr=[np.subtract(med, lo), np.subtract(hi, med)], fmt="o", color=OKABE["blue"], ms=3,
                capsize=2, elinewidth=0.6)
    for yi, m_, r in zip(y, med, lat):
        ax.text(float(r["max_s"]) * 1.3, yi, f"{_reader(r['tool'])}: {m_:.3g} s (n {r['n_calls']})", va="center",
                fontsize=8)
        L.add("F6", f"b.{r['tool']}", m_, lsrc, f"median_s ({r['source']})", unit="s", script=S)
    ax.set_xscale("log")
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_ylim(-0.6, len(lat) - 0.4)
    ax.set_xlim(0.3, 3e4)
    ax.set_xlabel("wall time per call (s)")
    ax.set_title("Tool latency, fresh process (median, range)", pad=4)
    panel_label(ax, "b", x=-0.03)

    # (c) certificate time by target type (V3, current checker)
    ax = axs[1, 0]
    csrc = "results/verification/v4/cert_times.csv"
    ct = [r for r in read_csv(csrc) if r["source"] == "V3"]
    # colour by the released-rule verdict (V14 re-judgment of the stored solves; the timings are those of the run)
    vsrc = "results/verification/v14/summary.json"
    rel = {c["cert"]: c["after"] for c in json.loads((ROOT / vsrc).read_text())["benchmark_changed"]}
    for r in ct:
        r["verdict"] = rel.get(r["cert_id"], r["verdict"])
    for k in ("certified", "undetermined", "refuted"):
        L.add("F6", f"c.released.{k}", sum(r["verdict"] == k for r in ct), vsrc,
              "V3 certificates by released-rule verdict (v14 benchmark_changed applied)", status="derived", script=S)
    types = ["static", "gap", "combined"]
    data = [[float(r["total_s"]) for r in ct if r["target_type"] == t] for t in types]
    ax.boxplot(data, positions=range(len(types)), widths=0.5, showfliers=False, patch_artist=True,
               medianprops=dict(color="k", lw=1), boxprops=dict(facecolor="#E8E8E8", lw=0.6),
               whiskerprops=dict(lw=0.6), capprops=dict(lw=0.6))
    rng = np.random.default_rng(1)
    vcol = {k: OUTCOME[k] for k in ("certified", "undetermined", "refuted")}
    for i, t in enumerate(types):
        rr = [r for r in ct if r["target_type"] == t]
        ax.scatter(i + rng.uniform(-0.18, 0.18, len(rr)), [float(r["total_s"]) for r in rr], s=8,
                   c=[vcol.get(r["verdict"], "k") for r in rr], edgecolors="k", lw=0.25, zorder=3)
        med = stt.median(float(r["total_s"]) for r in rr)
        ax.text(i + 0.3, med, f"{med:.0f} s", fontsize=8, va="center")
        L.add("F6", f"c.{t}.median", med, csrc, f"median total_s, source V3, target_type {t} (n {len(rr)})",
              status="derived", unit="s", script=S)
    ax.set_xticks(range(len(types)))
    ax.set_xticklabels([f"{t}\n(n {len(d)})" for t, d in zip(types, data)])
    ax.set_yscale("log")
    ax.set_ylabel("certificate wall time (s)")
    ax.set_title(f"Search benchmark certificates ({len(ct)})", pad=4)
    hd = [plt.Line2D([], [], marker="o", ls="", color=c_, mec="k", mew=0.25, ms=3, label=k) for k, c_ in vcol.items()]
    ax.legend(handles=hd, loc="upper left", fontsize=8, ncol=3, columnspacing=0.6)
    ax.set_ylim(30, 3000)
    panel_label(ax, "c", x=-0.14)
    L.add("F6", "c.n_V3", len(ct), csrc, "rows with source V3", status="derived", script=S)

    # (d) scaling; only the first and last resolution of each path is labelled
    ax = axs[1, 1]
    ssrc = "results/verification/v4/scaling.csv"
    allsc = read_csv(ssrc)
    sc = [r for r in allsc if r["mkl_threads"] == "16" and r["t_solve_s"]]
    lab = {"static": "static homogenization (CPU)", "bloch_cpu": "Bloch inertia count, 1 shift (CPU)",
           "bloch_gpu": "Bloch dense bands, 1 k (GPU)"}
    pcol = {"static": OKABE["blue"], "bloch_cpu": OKABE["green"], "bloch_gpu": OKABE["vermillion"]}
    # label offsets (points) and alignment for the first and last point of each path
    off = {"static": [((-4, 4), "right"), ((-4, 4), "right")], "bloch_cpu": [((4, -9), "left"), ((4, -9), "left")],
           "bloch_gpu": [((4, -9), "left"), ((-4, 4), "right")]}
    for pth in ("static", "bloch_cpu", "bloch_gpu"):
        rr = sorted([r for r in sc if r["path"] == pth], key=lambda r: int(r["ndof"]))
        nd = [int(r["ndof"]) for r in rr]
        tt = [float(r["t_solve_s"]) for r in rr]
        ax.loglog(nd, tt, "o-", color=pcol[pth], ms=3, label=lab[pth])
        for j, (xy_off, ha) in zip((0, -1), off[pth]):
            if pth == "bloch_gpu" and j == 0:
                continue   # same ndof as the CPU n 10 point, which carries the label
            ax.annotate(f"n {rr[j]['n']}", (nd[j], tt[j]), xytext=xy_off, textcoords="offset points", fontsize=8,
                        color=pcol[pth], ha=ha)
        L.add("F6", f"d.{pth}.series", len(rr), ssrc, "t_solve_s vs ndof at 16 threads", status="derived", script=S)
    skipped = [r for r in allsc if r["path"] == "bloch_gpu" and not r["t_solve_s"]]
    if skipped:
        r = skipped[0]
        last = sorted([q for q in sc if q["path"] == "bloch_gpu"], key=lambda q: int(q["ndof"]))[-1]
        ax.annotate(f"n {r['n']}: GPU out of memory", (int(last["ndof"]), float(last["t_solve_s"])),
                    xytext=(int(r["ndof"]) * 0.35, 0.03), fontsize=8, color=pcol["bloch_gpu"], ha="left",
                    arrowprops=dict(arrowstyle="-", lw=0.5, color=pcol["bloch_gpu"]))
        L.add("F6", "d.gpu_oom", f"n {r['n']}", ssrc, "skipped: " + r["skipped"][:40], status="verified", script=S)
    ax.set_xlabel("unknowns")
    ax.set_ylabel("solve time (s)")
    ax.set_ylim(0.008, 300)
    ax.set_title("Scaling with resolution (cube-and-bars)", pad=4)
    ax.legend(loc="upper left", fontsize=8)
    panel_label(ax, "d", x=-0.14)
    return style.save(fig, "F6_performance", FIGURES)


# ============================================================================================================ F10
@sources("results/bench/e4/scores.json", "results/bench/e4/analysis_A2.json")
def f10_agent(L: Ledger):
    _plt()
    ssrc, asrc = "results/bench/e4/scores.json", "results/bench/e4/analysis_A2.json"
    sc = [x for x in read_json(ssrc) if x["partition"] == "confirmatory"]
    a = read_json(asrc)
    assert a["amendment"] == "A2"
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(DOUBLE, 80 * MM), gridspec_kw=dict(width_ratios=[1, 1.3],
                                                                                   wspace=0.25))
    order = [("success", "success (release passes scorer check)"), ("correct_refusal", "correct refusal (proven)"),
             ("abstention", "abstention (unresolved)"), ("false_refusal", "false refusal (feasible)"),
             ("overclaim", "overclaim"), ("no_answer", "no answer")]
    arms = ["D", "B", "C"]
    armlab = {"D": "D\nLLM alone", "B": "B\n+ search\ntools", "C": "C\n+ bounds,\ncertify"}
    oc = collections.Counter((x["arm"], x["outcome"]) for x in sc)
    bottom = np.zeros(3)
    small = collections.defaultdict(list)    # segments too thin for an inside label: labelled at the right
    for key, lab in order:
        vals = np.array([oc.get((arm, key), 0) for arm in arms])
        ax.bar(range(3), vals, bottom=bottom, color=OUTCOME[key], edgecolor="k", lw=0.4, width=0.6, label=lab)
        for i, v in enumerate(vals):
            if v >= 3:
                ax.text(i, bottom[i] + v / 2, str(v), ha="center", va="center", fontsize=8,
                        color="white" if key in ("success", "correct_refusal", "false_refusal", "overclaim",
                                                 "no_answer") else "k")
            elif v:
                small[i].append((bottom[i] + v / 2, str(v)))
            L.add("F10", f"a.{arms[i]}.{key}", int(v), ssrc, f"count arm {arms[i]} outcome {key} (confirmatory)",
                  status="derived", script=S)
        bottom += vals
    n_b = int(bottom[0])
    assert all(b == n_b for b in bottom)
    for i, lst in small.items():      # push labels apart (top down) so thin neighbouring segments stay readable
        prev = n_b + 4.0
        for yy, t in sorted(lst, reverse=True):
            ty = min(yy, prev - 4.0)
            ax.annotate(t, (i + 0.3, yy), xytext=(i + 0.42, ty), ha="left", va="center", fontsize=8,
                        arrowprops=dict(arrowstyle="-", lw=0.4, color="k"))
            prev = ty
    ax.set_xticks(range(3))
    ax.set_xticklabels([armlab[a_] for a_ in arms])
    ax.set_ylabel(f"briefs (of {n_b} per arm)")
    ax.set_ylim(0, n_b)
    ax.set_xlim(-0.45, 2.7)
    ax.set_title("Outcomes per arm (Codex, repeat 1)", pad=4)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.27), ncol=2, fontsize=8)
    panel_label(ax, "a", x=-0.13)

    # (b) forest plot; each test is named above its interval so the panel needs no tick labels
    p = a["primary_C_minus_B_correct"]
    tests = [("H1 (primary): correct, C − B", p, None)]
    lab2 = {"false_refusal_B_minus_C": "false refusals, B − C", "correct_C_minus_D": "correct, C − D",
            "overclaim_B_minus_C": "overclaims, B − C", "unsupported_release_B_minus_C": "unsupported releases, B − C",
            "resolved_ambiguous_C_minus_B": "ambiguity resolved, C − B"}
    for k in ("correct_C_minus_D", "false_refusal_B_minus_C", "overclaim_B_minus_C", "unsupported_release_B_minus_C",
              "resolved_ambiguous_C_minus_B"):
        tests.append((lab2[k], a["secondary"][k], a["secondary"][k]["p_holm"]))
    for i, (lab, s, ph) in enumerate(tests):
        y = len(tests) - 1 - i
        colr = OKABE["vermillion"] if i == 0 else OKABE["blue"]
        bx.errorbar([s["diff"]], [y], xerr=[[s["diff"] - s["ci95"][0]], [s["ci95"][1] - s["diff"]]], fmt="o",
                    color=colr, ms=4, capsize=2, elinewidth=0.9)
        ptxt = f"p {s['p']:.1g}" if ph is None else f"Holm p {ph:.2g}"
        wb = dict(fc="white", ec="none", pad=0.6)
        bx.text(-0.28, y + 0.36, lab, va="center", ha="left", fontsize=8, bbox=wb, zorder=5)
        bx.text(1.0, y + 0.36, f"{s['diff']:+.3f}  {ptxt}  (n {s['n_specs']})", va="center", ha="right",
                fontsize=8, bbox=wb, zorder=5)
        L.add("F10", f"b.{lab}", f"{s['diff']:+.3f} [{s['ci95'][0]:.3f}, {s['ci95'][1]:.3f}]", asrc,
              "diff and ci95", script=S)
        L.add("F10", f"b.{lab}.p", f"{(s['p'] if ph is None else ph):.2g}", asrc,
              "p (permutation)" if ph is None else "p_holm", script=S)
    bx.axvline(0, color=OKABE["grey"], lw=0.6, zorder=0)
    bx.set_yticks([])
    bx.spines["left"].set_visible(False)
    bx.set_ylim(-0.5, len(tests) - 0.3)
    bx.set_xlim(-0.28, 1.0)
    bx.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    bx.set_xlabel("difference in per-spec mean (95 % CI)")
    bx.set_title("Amended confirmatory tests", pad=4)
    panel_label(bx, "b", x=-0.02)
    return style.save(fig, "F10_agent_evaluation", FIGURES)


# ============================================================================================================ F11
@sources("results/atlas/atlas_nu0.3.jsonl", "results/atlas/atlas_nu0.342.jsonl", "results/atlas/atlas_nu0.39.jsonl",
         "bench/v1/briefs/*.json", "results/verification/v14/bench/runs.csv")
def f11_atlas(L: Ledger):
    _plt()
    mats = {"316L": 0.3, "Ti6Al4V": 0.342, "PA12": 0.39}
    # certified records of atlas grid cells: E4 witnesses (bench/v1/briefs truth) and V3 final designs from the atlas
    cert = collections.defaultdict(set)
    for f in glob.glob(str(ROOT / "bench/v1/briefs/*.json")):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        t = d.get("truth") or {}
        if t.get("certificate") == "certified" and t.get("witness"):
            w = t["witness"]
            cert[mats[d["intended"]["material"]]].add(_key(w["kind"], w["params"]))
    nwit = sum(len(v) for v in cert.values())
    v3 = collections.defaultdict(set)
    for r in read_csv("results/verification/v14/bench/runs.csv"):
        if r["certified"] == "True" and r["from_atlas"] == "True":
            v3[float(r["nu"])].add(_key(r["final_kind"], json.loads(r["final_params"])))
    fig, axs = plt.subplots(1, 3, figsize=(DOUBLE, 70 * MM), sharey=True, gridspec_kw=dict(wspace=0.08))
    famlab = {"tpms": "TPMS", "struts": "struts", "resonator": "resonators"}
    for ax, (nu, fn) in zip(axs, ((0.3, "atlas_nu0.3.jsonl"), (0.342, "atlas_nu0.342.jsonl"),
                                  (0.39, "atlas_nu0.39.jsonl"))):
        src = f"results/atlas/{fn}"
        rows = [r for r in read_jsonl(src) if r.get("valid")]
        n_all = sum(1 for _ in open(ROOT / src, encoding="utf-8"))
        marked = 0
        for fam in ("tpms", "struts", "resonator"):
            rr = [r for r in rows if r["spec"]["family"] == fam and r["best_rel_gap"] > 0]
            x = np.array([r["E100"] for r in rr])
            y = np.array([r["best_rel_gap"] for r in rr])
            ax.scatter(x, y, s=3, color=FAMILY[fam], alpha=0.35, lw=0, label=famlab[fam], rasterized=True)
            # front: largest gap at or above each stiffness (non-dominated, maximize both)
            if len(x):
                o = np.argsort(-x)
                fx, fy, best = [], [], -1
                for i in o:
                    if y[i] > best:
                        best = y[i]
                        fx.append(x[i])
                        fy.append(y[i])
                ax.step(fx, fy, where="post", color=FAMILY[fam], lw=1.0)
                L.add("F11", f"nu{nu}.{fam}.front_points", len(fx), src, "non-dominated (E100, best_rel_gap) cells",
                      status="derived", script=S)
            L.add("F11", f"nu{nu}.{fam}.gap_cells", len(rr), src, "valid cells with best_rel_gap > 0",
                  status="derived", script=S)
        for keys, mk, lab in ((cert[nu], "o", "certified witness (agent experiment)"),
                              (v3[nu] - cert[nu], "D", "certified in search benchmark (atlas row)")):
            sel = [r for r in rows if _key(r["spec"]["kind"], r["spec"]["params"]) in keys]
            marked += len(sel)
            ax.scatter([r["E100"] for r in sel], [max(r["best_rel_gap"], 0.003) for r in sel], s=16, marker=mk,
                       facecolor="none", edgecolor="k", lw=0.7, label=lab, zorder=5)
            L.add("F11", f"nu{nu}.marked.{mk}", len(sel), src + " + " + ("bench/v1/briefs" if mk == "o" else
                                                                         "results/verification/v14/bench/runs.csv"),
                  "atlas rows matching certified records", status="derived", script=S)
        ng = sum(1 for r in rows if r["best_rel_gap"] <= 0)
        ax.set_xscale("log")
        ax.set_xlim(1.5e-4, 0.4)
        ax.set_ylim(0, 2.0)
        ax.set_xlabel(r"E100 / E$_s$ (search tier)")
        mname = [k for k, v in mats.items() if v == nu][0]
        ax.set_title(f"ν$_s$ = {nu} ({mname})", pad=4)
        ax.text(0.98, 0.97, f"{len(rows)} valid of {n_all} cells;\n{ng} without a gap (not shown)",
                transform=ax.transAxes, ha="right", va="top", fontsize=8, color=OKABE["grey"])
        L.add("F11", f"nu{nu}.valid", len(rows), src, "rows with valid", status="derived", script=S)
        L.add("F11", f"nu{nu}.rows", n_all, src, "line count", status="derived", script=S)
        L.add("F11", f"nu{nu}.no_gap", ng, src, "valid rows with best_rel_gap <= 0", status="derived", script=S)
    axs[0].set_ylabel("widest complete gap,\nwidth / mid frequency")
    h, l = axs[0].get_legend_handles_labels()
    uniq = dict(zip(l, h))
    for ax in axs[1:]:
        for hh, ll in zip(*ax.get_legend_handles_labels()):
            uniq.setdefault(ll, hh)
    leg = fig.legend(list(uniq.values()), list(uniq.keys()), loc="lower center", ncol=5, fontsize=8,
                     bbox_to_anchor=(0.5, -0.02), markerscale=1.5)
    for lh in leg.legend_handles:
        try:
            lh.set_alpha(1)
        except Exception:
            pass
    fig.subplots_adjust(bottom=0.27)
    for i, ax in enumerate(axs):
        panel_label(ax, "abc"[i], x=-0.04)
    L.add("F11", "certified_witness_cells", nwit, "bench/v1/briefs/*.json", "unique (material, witness) with "
          "truth.certificate == certified", status="derived", script=S)
    return style.save(fig, "F11_atlas_maps", FIGURES)


def _key(kind, params):
    return kind + json.dumps({k: (round(float(v), 5) if isinstance(v, (int, float)) else v)
                              for k, v in sorted(params.items())}, sort_keys=True)


ALL = [f3_stiffness, f4_bandgap, f5_search, f6_performance, f10_agent, f11_atlas]
