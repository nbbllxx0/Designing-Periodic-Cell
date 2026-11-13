"""V1b figures from the comparison JSON (data plots; regenerated from results/verification/v1b/summary.json).

    figures.py  -> results/verification/v1b/fig_v1b_stiffness.png (F3 panel), fig_v1b_bandedges.png (F4 panel)
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v1b"
FAM_C = {"tpms": "#1b6ca8", "struts": "#d9822b", "resonator": "#2a9d55"}
SHORT = {"tpms_schwarzp_d0.25_nu0.3": "P-net 0.25", "tpms_schwarzp_sheet_d0.2895_nu0.342": "P-sheet 0.29",
         "strut_bcc_R0.27_r0.06_nu0.342": "bcc R.27 r.06", "strut_octet_r0.06_nu0.3": "octet r.06",
         "thin_sl_c0.402_w0.061_nu0.3": "SL c.40 w.06", "thin_sl_c0.357_w0.109_nu0.3": "SL c.36 w.11"}
SET_STYLE = {"amm_path": ("o", "#555555", "amm path"), "amm_interior": ("s", "#1b6ca8", "amm interior"),
             "amm_adversarial": ("^", "#c0392b", "amm adversarial"), "own_adversarial": ("v", "#8e44ad", "own search"),
             "full_zone": ("D", "#2a9d55", "full zone (off wedge)")}
plt.rcParams.update({"font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "legend.fontsize": 7})


def stiffness(S):
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 3.6), gridspec_kw=dict(width_ratios=[1, 1.5]))
    a = ax[0]
    allv = []
    for cid, r in S.items():
        st = r.get("static")
        if not st:
            continue
        col = FAM_C[r["family"]]
        for qi, (q, mk) in enumerate((("E100", "o"), ("G", "s"), ("bulk", "^"))):
            e = st["quantities"][q]
            R, A = e["ref"]["R"], e["amm_ext"]
            lo, hi = e["amm_lower"], e["amm_upper"]
            if R <= 0:
                continue
            a.errorbar(R, A, yerr=[[max(A - lo, 0)], [max(hi - A, 0)]], fmt=mk, color=col, ms=3.5, lw=0.8,
                       capsize=1.5, mfc="white" if lo <= 0 else col)
            if "skfem_periodic" in e:
                sv = list(e["skfem_periodic"].values())[-1]
                a.plot(R, sv, "x", color="k", ms=3, lw=0.6)
            allv += [R, A]
    lim = [min(allv) / 1.6, max(allv) * 1.6]
    a.plot(lim, lim, "k-", lw=0.5)
    a.set_xscale("log"), a.set_yscale("log"), a.set_xlim(lim), a.set_ylim(lim)
    a.set_xlabel("independent reference (Q2-FCM, extrapolated) / $E_s$")
    a.set_ylabel("amm estimate / $E_s$ (bars: guarded bounds)")
    a.set_title("(a) Stiffness parity")
    for fam, c in FAM_C.items():
        a.plot([], [], "o", color=c, label=fam)
    for mk, lab in (("o", "E100"), ("s", "G"), ("^", "bulk")):
        a.plot([], [], mk, color="grey", label=lab)
    a.plot([], [], "x", color="k", label="scikit-fem (n=16)")
    a.legend(loc="upper left", frameon=False, ncol=2)
    b = ax[1]
    y, labels = 0, []
    for cid, r in S.items():
        st = r.get("static")
        if not st:
            continue
        for q in ("E100", "G", "bulk", "density"):
            e = st["quantities"][q]
            R = abs(e["ref"]["R"])
            u2 = 2 * e["ref"]["u"] / R * 100
            lo, hi = (e["amm_lower"] - e["ref"]["R"]) / R * 100, (e["amm_upper"] - e["ref"]["R"]) / R * 100
            col = FAM_C[r["family"]]
            X = 40
            b.plot([max(lo, -X), min(hi, X)], [y, y], "-", color=col, lw=3, alpha=0.35, solid_capstyle="butt")
            b.plot(np.clip(e["delta"] * 100, -X, X), y, "o", color=col, ms=3.5)
            b.plot([-u2, u2], [y, y], "|", color="k", ms=5, mew=0.8)
            if "skfem_delta" in e:
                b.plot(e["skfem_delta"] * 100, y, "x", color="k", ms=3)
            if lo < -X:
                b.annotate(f"lower {lo:.0f}%", (-X + 0.5, y - 0.35), fontsize=5.5, va="center", ha="left")
            if hi > X:
                b.annotate(f"upper +{hi:.0f}%", (X - 0.5, y - 0.35), fontsize=5.5, va="center", ha="right")
            labels.append(f"{SHORT.get(cid, cid)} {q}")
            y += 1
        y += 0.6
        labels.append("")
    b.axvline(0, color="k", lw=0.5)
    ticks = [i for i, l in enumerate([l for l in labels])]
    yy, lab, cur = [], [], 0
    for cid, r in S.items():
        if not r.get("static"):
            continue
        for q in ("E100", "G", "bulk", "density"):
            yy.append(cur), lab.append(f"{SHORT.get(cid, cid)}  {q}")
            cur += 1
        cur += 0.6
    b.set_yticks(yy, lab, fontsize=6)
    b.invert_yaxis()
    b.set_xlim(-40, 40)
    b.plot([], [], "o", color="grey", label="amm estimate")
    b.plot([], [], "-", color="grey", lw=3, alpha=0.4, label="amm guarded [lower, upper]")
    b.plot([], [], "|", color="k", ms=6, label="reference $\pm 2u$")
    b.plot([], [], "x", color="k", label="scikit-fem")
    b.legend(loc="upper center", bbox_to_anchor=(0.45, -0.12), ncol=2, frameon=False, fontsize=6)
    b.set_xlabel("signed difference from the reference (%)", labelpad=1)
    b.set_title("(b) Two-sided differences from the reference")
    fig.tight_layout()
    fig.savefig(OUT / "fig_v1b_stiffness.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def bandedges(S):
    gaps = {cid: r for cid, r in S.items() if r.get("gap")}
    sets = list(SET_STYLE)
    fig, ax = plt.subplots(1, 3, figsize=(7.2, 3.9), gridspec_kw=dict(width_ratios=[1.3, 1, 1]), sharey=True)
    a = ax[0]
    for y, (cid, r) in enumerate(gaps.items()):
        g = r["gap"]
        R1, u1, R2, u2 = g["ref_lo"]["R"], g["ref_lo"]["u"], g["ref_hi"]["R"], g["ref_hi"]["u"]
        a.fill_betweenx([y - 0.32, y + 0.32], R1, R2, color="#e4e4e4", lw=0)
        for R, u in ((R1, u1), (R2, u2)):
            a.fill_betweenx([y - 0.32, y + 0.32], R - 2 * u, R + 2 * u, color="#8a8a8a", lw=0)
        s_lo, s_hi = g["safe_interval"]
        a.plot([s_lo, s_hi], [y - 0.16, y - 0.16], "-", color=FAM_C[r["family"]], lw=2.5)
        for c in g["claims"]:
            yy = y + 0.02 if c["claim"] == "nominal" else y + 0.18
            a.plot([c["f_lo"], c["f_hi"]], [yy, yy], "-", color="k" if c["claim"] == "nominal" else "#c0392b", lw=1.2)
    a.set_yticks(range(len(gaps)), [SHORT.get(c, c) for c in gaps])
    a.set_ylim(len(gaps) - 0.5, -0.5)
    a.set_xlabel("$f^* = f a / c_t$")
    a.set_title("(a) Gap edges")
    off = {s_: (i - 2) * 0.055 for i, s_ in enumerate(sets)}
    b, c2 = ax[1], ax[2]
    for y, (cid, r) in enumerate(gaps.items()):
        g = r["gap"]
        for e in (g.get("per_k_sampled") or {}).get("rows", []):
            if "d_lo_sampled" not in e:
                continue
            mk, col, lab = SET_STYLE.get(e["set"], ("o", "k", e["set"]))
            b.plot(e["d_lo_sampled"] / g["ref_lo"]["R"] * 100, y - 0.17 + off.get(e["set"], 0), mk, color=col,
                   ms=2.6, mfc="none", mew=0.7)
            b.plot(e["d_hi_sampled"] / g["ref_hi"]["R"] * 100, y + 0.17 + off.get(e["set"], 0), mk, color=col,
                   ms=2.6, mew=0.7)
        for e in g.get("per_k_extrapolated") or []:
            if "lo" not in e:
                continue
            mk, col, _ = SET_STYLE.get(e["set"], ("o", "k", e["set"]))
            for side, sgn in (("lo", -1), ("hi", 1)):
                d = e[side]
                q, am = d["q2"], d["amm"]
                XC, yy = 40, y + sgn * 0.17 + off.get(e["set"], 0)
                x, err = d["delta"] * 100, 2 * np.hypot(q["u"], am["u"]) / q["R"] * 100
                c2.plot([max(x - err, -XC), min(x + err, XC)], [yy, yy], "-", color=col, lw=0.6)
                c2.plot(x, yy, mk, color=col, ms=2.6, mfc="none" if side == "lo" else col)
                if x - err < -XC:
                    c2.plot(-XC, yy, "<", color=col, ms=2.5)
    for ax_ in (b, c2):
        ax_.axvline(0, color="k", lw=0.5)
        for y in range(len(gaps)):
            ax_.axhline(y + 0.5, color="#dddddd", lw=0.5)
    b.set_xlabel("amm n20 $-$ Q2 n$_1$ (%)")
    b.set_title("(b) Per k, sampled level")
    c2.set_xlim(-41, 41)
    c2.set_xlabel("amm $-$ Q2, extrapolated (%)")
    c2.set_title("(c) Per k, extrapolated")
    handles = [plt.Line2D([], [], ls="", marker="s", color="#e4e4e4", label="reference gap", ms=6),
               plt.Line2D([], [], ls="", marker="s", color="#8a8a8a", label="reference edge $\pm2u$", ms=6),
               plt.Line2D([], [], ls="-", color="grey", lw=2.5, label="amm safe interval"),
               plt.Line2D([], [], ls="-", color="k", label="nominal claim"),
               plt.Line2D([], [], ls="-", color="#c0392b", label="marginal claim")]
    handles += [plt.Line2D([], [], ls="", marker=m, color=c, label=l, ms=4) for m, c, l in SET_STYLE.values()]
    handles += [plt.Line2D([], [], ls="", marker="o", mfc="none", color="k", label="band below gap (upper row)"),
                plt.Line2D([], [], ls="", marker="o", color="k", label="band above gap (lower row)")]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=6, frameon=False)
    fig.tight_layout(rect=(0, 0.17, 1, 1))
    fig.savefig(OUT / "fig_v1b_bandedges.png", dpi=200)
    plt.close(fig)


def main():
    S = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    stiffness(S)
    bandedges(S)
    print("figures written")


if __name__ == "__main__":
    main()
