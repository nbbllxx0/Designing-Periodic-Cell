"""V6 data figures from the result files only (no diagrams).

    python scripts/verify/v6/figures.py
fig_v6_mount.png (F8): static check of the mount and 6-cell transmission vs the reference, certified band shaded.
fig_v6_gallery.png (F7): per case: exported cell STL, tiled STL, search-tier band diagram, evidence summary.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

import stl_recheck as sr  # noqa: E402

V6 = Path(__file__).resolve().parents[3] / "results" / "verification" / "v6"
C_DES, C_REF = "#1f5fa8", "#c0502a"
plt.rcParams.update({"font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8, "legend.fontsize": 7,
                     "xtick.labelsize": 7, "ytick.labelsize": 7, "font.family": "DejaVu Sans"})


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def label_of(d):
    p = d["params"]
    return d["kind"].replace("_", " ") + " " + ", ".join(f"{k} {v:.3g}" if isinstance(v, float) else f"{v}"
                                                        for k, v in p.items())


# --------------------------------------------------------------------------------------------------------- F8
def fig_mount():
    md, mr = J(V6 / "case1/macro_design.json"), J(V6 / "case1/macro_reference.json")
    ch = {(lab, n): J(V6 / f"case1/chain_{lab}_n{n}.json") for lab in ("design", "reference") for n in (16, 24)}
    sd = J(V6 / "case1/session_design/summary.json")
    gap = sd["certificate_summary"]["gap"]
    hz = ch[("design", 24)]["hz_per_f_star"]
    band = ch[("design", 24)]["band_Hz"]
    safe = [x * hz for x in gap["safe_interval"]]
    fig = plt.figure(figsize=(7.2, 5.6), dpi=300)
    gs = fig.add_gridspec(2, 6, hspace=0.62, wspace=1.6)
    # (a) stiffness
    ax = fig.add_subplot(gs[0, 0:2])
    kreq = md["k_req_N_per_m"] / 1e6
    x = np.arange(3)
    w = 0.36
    for i, (m, lab, c) in enumerate(((md, "design", C_DES), (mr, "reference", C_REF))):
        ks = [m["A2"]["uniaxial_estimate_kN_per_mm"], m["A2"]["k_kN_per_mm"],
              m["A2"]["k_kN_per_mm"] * m["A2s"]["ratio_used"]]
        ax.bar(x + (i - 0.5) * w, ks, w, color=c, alpha=0.9, label=lab)
    ax.axhline(kreq, color="k", lw=0.9, ls="--", label=f"required {kreq:.1f}")
    ax.set_xticks(x, ["E100 A/H", "FE 6x6x6", "size-corr."])
    ax.set_ylabel("mount stiffness (kN/mm)")
    ax.set_ylim(0, 11.5)
    ax.set_title("(a) mount stiffness, guarded C*", loc="left")
    ax.legend(frameon=False, loc="upper left", ncol=2, fontsize=6.3, columnspacing=0.8)
    # (b) 3x3x3 voxel vs homogenized at the same resolution
    ax = fig.add_subplot(gs[0, 2:4])
    ns = [16, 24, 32]
    for m, lab, c in ((md, "design", C_DES), (mr, "reference", C_REF)):
        sc = m["E_s"] * m["cell_size_m"] / 1e6
        kv = [m["voxel_3x3x3"][f"n{n}"]["k_star"] * sc for n in ns]
        kh = [m["voxel_3x3x3"][f"n{n}"]["k_star_hom_same_n"] * sc for n in ns]
        ax.plot([1 / n for n in ns], kv, "o-", color=c, ms=3, lw=1, label=f"{lab}: voxel block")
        ax.plot([1 / n for n in ns], kh, "s--", color=c, ms=2.5, lw=0.8, mfc="none", label=f"{lab}: homogenized")
    ax.set_xlabel("voxel size h / a")
    ax.set_ylabel("3x3x3 block stiffness (kN/mm)")
    ax.set_title("(b) finite 3x3x3 block, same n", loc="left")
    ax.legend(frameon=False, loc="upper left", fontsize=5.8)
    ax.set_xlim(0.025, 0.068)
    ax.set_ylim(3.9, 5.6)
    # (c) band-mean summary
    ax = fig.add_subplot(gs[0, 4:6])
    labels, vd, vr = [], [], []
    for dk, name in (("longitudinal", "long."), ("shear_x", "shear")):
        for n in (16, 24):
            labels.append(name + "\nn=" + str(n))
            vd.append(ch[("design", n)]["band_metrics"][dk]["mean_dB"])
            vr.append(ch[("reference", n)]["band_metrics"][dk]["mean_dB"])
    x = np.arange(len(labels))
    ax.bar(x - 0.2, vr, 0.4, color=C_REF, label="reference")
    ax.bar(x + 0.2, vd, 0.4, color=C_DES, label="design")
    for i in range(len(x)):
        ax.text(x[i], vd[i] - 3, f"{vd[i] - vr[i]:.0f}", ha="center", va="top", fontsize=6.3)
    ax.axhline(0, color="k", lw=0.5)
    ax.axhline(-20, color="0.5", lw=0.5, ls=":")
    ax.set_xticks(x, labels, fontsize=6.3)
    ax.set_ylabel("band-mean T in claim (dB)")
    ax.set_title("(c) design - reference (dB)", loc="left")
    ax.set_ylim(-130, 45)
    ax.legend(frameon=False, loc="upper right", fontsize=6.0, ncol=2, columnspacing=0.6, handlelength=1.2)
    # (d)-(e) transmission
    for j, (dk, name) in enumerate((("2", "longitudinal (z) drive"), ("0", "shear (x) drive"))):
        ax = fig.add_subplot(gs[1, 3 * j:3 * j + 3])
        ax.axvspan(safe[0] / 1e3, min(safe[1], 1.5 * band[1]) / 1e3, color="#9ecae1", alpha=0.22, lw=0,
                   label="certified safe interval")
        ax.axvspan(band[0] / 1e3, band[1] / 1e3, color="#6baed6", alpha=0.45, lw=0, label="certified claim")
        for lab, c in (("design", C_DES), ("reference", C_REF)):
            for n, ls in ((24, "-"), (16, "--")):
                r = ch[(lab, n)]
                nb = r["n_band"]
                f = np.array(r["f_star"][nb:]) * hz / 1e3
                T = 20 * np.log10(np.maximum(np.array(r["T"][dk][nb:]), 1e-30))
                ax.plot(f, T, ls, color=c, lw=0.9 if n == 24 else 0.6, label=f"{lab}, n = {n}")
        ax.set_xlabel("frequency (kHz)")
        ax.set_ylabel("T = 20 log10 |u_out / u_in| (dB)")
        ax.set_title(f"({'de'[j]}) 6-cell slab (k_perp = 0), {name}", loc="left")
        ax.set_xlim(0, 1.5 * band[1] / 1e3)
        ax.set_ylim(-140, 45)
        if j == 0:
            ax.legend(frameon=False, loc="lower left", fontsize=5.8)
    fig.savefig(V6 / "fig_v6_mount.png", bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------------------------------------- F7
def render(ax, tri, title, max_tri=120000, elev=24, azim=-58):
    if len(tri) > max_tri:
        tri = tri[np.random.default_rng(0).choice(len(tri), max_tri, replace=False)]
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-30)
    light = np.array([0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    sh = 0.35 + 0.65 * np.clip(nrm @ light, 0, 1)
    col = np.outer(sh, np.array([0.55, 0.65, 0.78]))
    pc = Poly3DCollection(tri, facecolors=col, edgecolors=col, linewidths=0.05, rasterized=True)
    ax.add_collection3d(pc)
    lo, hi = tri.reshape(-1, 3).min(0), tri.reshape(-1, 3).max(0)
    ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(hi - lo)
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.set_title(title, fontsize=7)


def bands_panel(ax, ev_row, gap_hz, safe_hz, title):
    b = ev_row["bands"]
    f = np.array(b["f_star"]) * b["hz_per_f_star"] / 1e3
    x = np.arange(f.shape[0])
    ax.plot(x, f, color="0.25", lw=0.6)
    if gap_hz:
        ax.axhspan(gap_hz[0] / 1e3, gap_hz[1] / 1e3, color="#9ecae1", alpha=0.6, lw=0)
    if safe_hz:
        ax.axhspan(safe_hz[0] / 1e3, safe_hz[1] / 1e3, color="#9ecae1", alpha=0.2, lw=0)
    ax.set_xticks([t[0] for t in b["k_ticks"]], [t[1].replace("G", "Γ") for t in b["k_ticks"]])
    ax.set_xlim(0, x[-1])
    top = 2.2 * gap_hz[1] / 1e3 if gap_hz else f.max()
    ax.set_ylim(0, min(top, f.max()))
    ax.set_ylabel("frequency (kHz)")
    ax.set_title(title, fontsize=7)


def fig_gallery():
    cases = [("Case 1 mount, design", V6 / "case1/session_design", V6 / "case1/recheck_design.json"),
             ("Case 1 reference", V6 / "case1/session_reference", V6 / "case1/recheck_reference.json"),
             ("Case 2 filter, PA12", V6 / "case2/session_PA12", V6 / "case2/recheck_PA12.json"),
             ("Case 2 filter, 316L", V6 / "case2/session_316L", V6 / "case2/recheck_316L.json")]
    cases = [c for c in cases if (c[1] / "summary.json").exists()]
    fig = plt.figure(figsize=(7.2, 1.85 * len(cases)), dpi=300)
    gs = fig.add_gridspec(len(cases), 4, width_ratios=[0.9, 1.0, 1.15, 1.45], wspace=0.25, hspace=0.45)
    for i, (title, sd, rc) in enumerate(cases):
        s = J(sd / "summary.json")
        d = s["released"] or s["certify"][0]["design"]
        ex = s["calls"]["export"]["result"]
        cell = sr.read_stl(sd / ex["files"]["cell"]["path"])
        tiled = sr.read_stl(sd / ex["files"]["tiled"]["path"])
        render(fig.add_subplot(gs[i, 0], projection="3d"), cell, f"{title}\ncell.stl ({len(cell)} tri)")
        render(fig.add_subplot(gs[i, 1], projection="3d"), tiled, "tiled 3x3x3 STL", max_tri=10 ** 7)
        ev = next(x for x in s["calls"]["evaluate"]["result"]["results"] if x["design"] == d)
        cs = s["certificate_summary"] or {}
        tg = s["calls"]["set_target"]["result"]["normalized"]
        hz = ev["bands"]["hz_per_f_star"]
        gap_hz = [tg["gap"]["f_lo"] * hz, tg["gap"]["f_hi"] * hz] if "gap" in tg else None
        safe = (cs.get("gap") or {}).get("safe_interval")
        safe_hz = [safe[0] * hz, safe[1] * hz] if safe else None
        bands_panel(fig.add_subplot(gs[i, 2]), ev, gap_hz, safe_hz, "bands (search tier)")
        ax = fig.add_subplot(gs[i, 3])
        ax.set_axis_off()
        mat = s["config"]["material"]
        E = {"PA12": 1.7e9, "316L": 193e9}[mat]
        lines = [f"{mat}, a = {s['config']['cell_size_mm']} mm", label_of(d),
                 f"certificate: {cs.get('verdict', 'none')}; as-built +-0.01a robust: {cs.get('robust')}"]
        st = (cs.get("static") or {}).get("bounds", {})
        if "E100" in st and "E100_min" in tg:
            lines.append(f"guarded E100 >= {st['E100']['lower'] * E / 1e6:.1f} MPa (target {tg['E100_min'] * E / 1e6:.0f})")
        if safe_hz:
            lines.append(f"claim {gap_hz[0] / 1e3:.2f}-{gap_hz[1] / 1e3:.2f} kHz; safe {safe_hz[0] / 1e3:.2f}-{safe_hz[1] / 1e3:.2f} kHz")
        sc = s["calls"]["screen_manufacturing"]["result"]
        mf = sc["min_feature"]
        lines.append(f"screen: {sc['verdict']}; min solid {mf['solid_est_mm']:.2f} mm "
                     f"(limit {mf['printer_limit_mm']:.1f})")
        if Path(rc).exists():
            r = J(rc)
            dd = r["static"]["diff_extrapolated"]
            lines.append(f"STL recheck: {'pass' if r['passed'] else 'FAIL'}; density {100 * dd['density']:+.2f} %, "
                         f"E100 {100 * dd['E100']:+.2f} %")
            if "gap" in r:
                sf = r["gap"]["safe_interval"]
                lines.append(f"  gap {r['gap']['verdict']['verdict']}" + (f", safe {sf[0] * hz / 1e3:.2f}-"
                                                                          f"{sf[1] * hz / 1e3:.2f} kHz" if sf and sf[0] else ""))
        ax.text(0.0, 0.95, "\n".join(lines), va="top", ha="left", fontsize=6.3, family="DejaVu Sans",
                transform=ax.transAxes, linespacing=1.35)
    fig.savefig(V6 / "fig_v6_gallery.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    which = sys.argv[1:] or ["mount", "gallery"]
    if "mount" in which:
        fig_mount()
    if "gallery" in which:
        fig_gallery()
    print("figures written")
