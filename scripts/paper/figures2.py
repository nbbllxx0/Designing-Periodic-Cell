"""Figures of batch 2 (plan item A1): F2 (annotated GUI, mount case), F7 (case gallery), F8 (mount checks), drawn
from result files only. Style: scripts/paper/style.py (8 pt at print width).

F7 and F8 are regenerated here from the V6 data files (session summaries, exported STL files, macro and chain JSON);
the V6 PNGs in results/verification/v6/ are not used. F2 places the V6 GUI screenshots unchanged (the caption band
that the V6 walkthrough script painted above each screenshot is cropped off; no GUI pixel is altered) and adds
region markers in the margins.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

import style
from common import FIGURES, ROOT, Ledger, read_json
from style import DOUBLE, MM, OKABE, panel_label

S = "scripts/paper/figures2.py"
V6 = "results/verification/v6"
plt = None
C_DES, C_REF = OKABE["blue"], OKABE["vermillion"]
GAP_CLAIM, GAP_SAFE = "#9ecae1", "#deebf7"


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


def J(p):
    return read_json(p)


# ============================================================================================================ F8
@sources(f"{V6}/case1/macro_design.json", f"{V6}/case1/macro_reference.json",
         f"{V6}/case1/chain_design_n16.json", f"{V6}/case1/chain_design_n24.json",
         f"{V6}/case1/chain_reference_n16.json", f"{V6}/case1/chain_reference_n24.json",
         f"{V6}/case1/session_design/summary.json")
def f8_mount(L: Ledger):
    _plt()
    md, mr = J(f"{V6}/case1/macro_design.json"), J(f"{V6}/case1/macro_reference.json")
    ch = {(lab, n): J(f"{V6}/case1/chain_{lab}_n{n}.json") for lab in ("design", "reference") for n in (16, 24)}
    sd = J(f"{V6}/case1/session_design/summary.json")
    gap = sd["certificate_summary"]["gap"]
    hz = ch[("design", 24)]["hz_per_f_star"]
    band = ch[("design", 24)]["band_Hz"]
    safe = [x * hz for x in gap["safe_interval"]]
    L.add("F8", "claim_band_Hz", f"{band[0]:.0f}-{band[1]:.0f}", f"{V6}/case1/chain_design_n24.json", "band_Hz",
          unit="Hz", script=S)
    L.add("F8", "safe_interval_kHz", f"{safe[0] / 1e3:.2f}-{safe[1] / 1e3:.2f}", f"{V6}/case1/session_design/summary.json",
          "certificate_summary.gap.safe_interval x hz_per_f_star", status="derived", unit="kHz", script=S)
    fig = plt.figure(figsize=(DOUBLE, 140 * MM))
    gs = fig.add_gridspec(2, 6, height_ratios=[1, 1.05], hspace=0.55, wspace=2.6, bottom=0.16, top=0.95,
                          left=0.07, right=0.99)

    # (a) mount stiffness
    ax = fig.add_subplot(gs[0, 0:2])
    kreq = md["k_req_N_per_m"] / 1e6
    x = np.arange(3)
    w = 0.38
    for i, (m, lab, c, src) in enumerate(((md, "design", C_DES, "macro_design.json"),
                                         (mr, "reference", C_REF, "macro_reference.json"))):
        ks = [m["A2"]["uniaxial_estimate_kN_per_mm"], m["A2"]["k_kN_per_mm"],
              m["A2"]["k_kN_per_mm"] * m["A2s"]["ratio_used"]]
        ax.bar(x + (i - 0.5) * w, ks, w, color=c, label=lab)
        for nm, k in zip(("uniaxial", "fe_6x6x6", "size_corrected"), ks):
            L.add("F8", f"a.{lab}.{nm}", k, f"{V6}/case1/{src}",
                  "A2.uniaxial_estimate / A2.k / A2.k x A2s.ratio_used", unit="kN/mm",
                  status="verified" if nm != "size_corrected" else "derived", script=S)
    ax.axhline(kreq, color="k", lw=0.8, ls="--", label=f"required {kreq:.1f}")
    L.add("F8", "a.k_required", kreq, f"{V6}/case1/macro_design.json", "k_req_N_per_m / 1e6", unit="kN/mm",
          status="derived", script=S)
    ax.set_xticks(x)
    ax.set_xticklabels(["E100\nA / H", "FE\n6×6×6", "size-\ncorr."])
    ax.set_ylabel("mount stiffness (kN/mm)")
    ax.set_ylim(0, 13.5)
    ax.set_yticks([0, 2, 4, 6, 8])
    ax.set_title("Mount stiffness", pad=4)
    ax.legend(loc="upper left", ncol=2, columnspacing=0.8, handlelength=1.2)
    panel_label(ax, "a", x=-0.32)

    # (b) 3x3x3 voxel block vs homogenized at the same n
    ax = fig.add_subplot(gs[0, 2:4])
    ns = [16, 24, 32]
    for m, lab, c, src in ((md, "design", C_DES, "macro_design.json"), (mr, "reference", C_REF, "macro_reference.json")):
        sc = m["E_s"] * m["cell_size_m"] / 1e6
        kv = [m["voxel_3x3x3"][f"n{n}"]["k_star"] * sc for n in ns]
        kh = [m["voxel_3x3x3"][f"n{n}"]["k_star_hom_same_n"] * sc for n in ns]
        ax.plot([1 / n for n in ns], kv, "o-", color=c, ms=3)
        ax.plot([1 / n for n in ns], kh, "s--", color=c, ms=3, mfc="white", lw=0.8)
        ax.text(1 / 16 - 0.002, kv[0] + 0.08, lab, color=c, ha="right", va="bottom", fontsize=8)
        L.add("F8", f"b.{lab}.series", len(ns), f"{V6}/case1/{src}",
              "voxel_3x3x3.n*.k_star and k_star_hom_same_n x E_s a", status="derived", script=S)
        r32 = m["voxel_3x3x3"]["n32"]["ratio_same_n"]
        L.add("F8", f"b.{lab}.ratio_n32", f"{r32:.4f}", f"{V6}/case1/{src}", "voxel_3x3x3.n32.ratio_same_n",
              script=S)
    ax.plot([], [], "o-", color="0.3", ms=3, label="voxel block")
    ax.plot([], [], "s--", color="0.3", ms=3, mfc="white", lw=0.8, label="homogenized")
    ax.set_xlabel("voxel size h / a")
    ax.set_ylabel("block stiffness (kN/mm)")
    ax.set_title("3×3×3 block, same n", pad=4)
    ax.set_xlim(0.028, 0.066)
    ax.set_ylim(3.6, 5.4)
    ax.legend(loc="lower right", handlelength=1.8)
    panel_label(ax, "b", x=-0.32)

    # (c) band means and the design - reference difference
    ax = fig.add_subplot(gs[0, 4:6])
    labels, vd, vr = [], [], []
    for dk, name in (("longitudinal", "long."), ("shear_x", "shear")):
        for n in (16, 24):
            labels.append(f"{name}\nn {n}")
            vd.append(ch[("design", n)]["band_metrics"][dk]["mean_dB"])
            vr.append(ch[("reference", n)]["band_metrics"][dk]["mean_dB"])
            L.add("F8", f"c.{dk}.n{n}.delta", f"{vd[-1] - vr[-1]:.1f}", f"{V6}/case1/chain_*_n{n}.json",
                  f"band_metrics.{dk}.mean_dB design - reference", status="derived", unit="dB", script=S)
    x = np.arange(len(labels))
    ax.bar(x - 0.2, vr, 0.4, color=C_REF)
    ax.bar(x + 0.2, vd, 0.4, color=C_DES)
    for i in range(len(x)):
        ax.text(x[i] + 0.2, vd[i] - 4, f"{vd[i] - vr[i]:.0f}", ha="center", va="top", fontsize=8)
    ax.axhline(0, color="k", lw=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("band-mean T (dB)")
    ax.set_title("In-band transmission", pad=4)
    ax.set_ylim(-165, 25)
    ax.text(3.45, -160, "numbers: design − reference", ha="right", va="bottom", fontsize=8)
    panel_label(ax, "c", x=-0.32)

    # (d)-(e) transmission spectra
    for j, (dk, name) in enumerate((("2", "Longitudinal drive (z)"), ("0", "Shear drive (x)"))):
        ax = fig.add_subplot(gs[1, 3 * j:3 * j + 3])
        ax.axvspan(safe[0] / 1e3, min(safe[1], 1.5 * band[1]) / 1e3, color=GAP_SAFE, lw=0,
                   label="guarded safe interval")
        ax.axvspan(band[0] / 1e3, band[1] / 1e3, color=GAP_CLAIM, lw=0, label="claimed gap")
        for lab, c in (("design", C_DES), ("reference", C_REF)):
            for n, ls, lw in ((24, "-", 1.0), (16, "--", 0.6)):
                r = ch[(lab, n)]
                nb = r["n_band"]
                f = np.array(r["f_star"][nb:]) * hz / 1e3
                T = 20 * np.log10(np.maximum(np.array(r["T"][dk][nb:]), 1e-30))
                ax.plot(f, T, ls, color=c, lw=lw, label=f"{lab}, n {n}")
                L.add("F8", f"{'de'[j]}.{lab}.n{n}.series", len(f), f"{V6}/case1/chain_{lab}_n{n}.json",
                      f"20 log10 T['{dk}'] over f_star[n_band:]", status="derived", script=S)
        ax.set_xlabel("frequency (kHz)")
        ax.set_ylabel("transmission (dB)")
        ax.set_title(name, pad=4)
        ax.set_xlim(0, 1.5 * band[1] / 1e3)
        ax.set_ylim(-145, 45)
        panel_label(ax, "de"[j], x=-0.1)
        if j == 0:
            h, lab_ = ax.get_legend_handles_labels()
    fig.legend(h, lab_, loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.0), columnspacing=1.5,
               handlelength=1.8)
    return style.save(fig, "F8_mount_checks", FIGURES)


# ============================================================================================================ F7
def _read_stl(p: Path) -> np.ndarray:
    b = p.read_bytes()
    n = struct.unpack("<I", b[80:84])[0]
    rec = np.frombuffer(b, dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")], count=n, offset=84)
    return rec["v"].astype(np.float64)


def _render(ax, tri, elev=24, azim=-58):
    """Orthographic flat-shaded render of a triangle soup (painter's algorithm, back faces culled)."""
    from matplotlib.collections import PolyCollection
    e, a = np.radians(elev), np.radians(azim)
    R = np.array([[-np.sin(a), np.cos(a), 0],
                  [-np.sin(e) * np.cos(a), -np.sin(e) * np.sin(a), np.cos(e)],
                  [np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)]])
    P = tri @ R.T
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-30)
    vis = (nrm @ R[2]) > 0
    P, nrm = P[vis], nrm[vis]
    order = np.argsort(P[:, :, 2].mean(1))
    P, nrm = P[order], nrm[order]
    light = np.array([0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    sh = 0.35 + 0.65 * np.clip(nrm @ light, 0, 1)
    col = np.outer(sh, [0.55, 0.65, 0.78])
    ax.add_collection(PolyCollection(P[:, :, :2], facecolors=col, edgecolors=col, linewidths=0.1, rasterized=True))
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.set_axis_off()


F7_CASES = [("Mount, design", "case1/session_design", "case1/recheck_design.json", 1.70e9),
            ("Mount, reference", "case1/session_reference", "case1/recheck_reference.json", 1.70e9),
            ("Filter, PA12", "case2/session_PA12", "case2/recheck_PA12.json", 1.70e9),
            ("Filter, 316L", "case2/session_316L", "case2/recheck_316L.json", 193e9)]


RESCORE = "results/verification/v14/engineering.json"
RECHECK = "results/verification/v14/rechecks.json"
FINE = "results/verification/v15/filters.json"
FINE_RC = "results/verification/v16/recheck_PA12.json"  # PA12 export, n 30/40/60
FINE_RC_316L = "results/verification/v16/recheck_316L.json"  # 316L export, n 30/40/60 (after the order-test fix)
REJUDGE = "results/verification/v19/rejudge.json"  # V15 finer checks re-judged after the order-test fix


@sources(*[f"{V6}/{c[1]}/summary.json" for c in F7_CASES], *[f"{V6}/{c[2]}" for c in F7_CASES], RESCORE, RECHECK, FINE, FINE_RC, FINE_RC_316L, REJUDGE,
         f"{V6}/case1/session_design/exports", f"{V6}/case1/session_reference/exports",
         f"{V6}/case2/session_PA12/exports", f"{V6}/case2/session_316L/exports")
def f7_cases(L: Ledger):
    _plt()
    n = len(F7_CASES)
    fig = plt.figure(figsize=(DOUBLE, 42 * MM * n))
    gs = fig.add_gridspec(n, 4, width_ratios=[0.8, 0.95, 1.15, 1.5], wspace=0.5, hspace=0.42)
    for i, (title, sdir, rc, E_s) in enumerate(F7_CASES):
        sp = f"{V6}/{sdir}/summary.json"
        s = J(sp)
        d = s["released"]
        ex = s["calls"]["export"]["result"]["files"]
        cell = _read_stl(ROOT / V6 / sdir / ex["cell"]["path"])
        tiled = _read_stl(ROOT / V6 / sdir / ex["tiled"]["path"])
        L.add("F7", f"{title}.cell_triangles", len(cell), f"{V6}/{sdir}/{ex['cell']['path']}", "STL triangle count",
              status="derived", script=S)
        L.add("F7", f"{title}.tiled_triangles", len(tiled), f"{V6}/{sdir}/{ex['tiled']['path']}",
              "STL triangle count", status="derived", script=S)
        ax = fig.add_subplot(gs[i, 0])
        _render(ax, cell)
        if i == 0:
            ax.set_title("exported cell STL", pad=2, loc="center", fontweight="normal")
        panel_label(ax, "abcd"[i], x=0.0, y=0.80)
        ax = fig.add_subplot(gs[i, 1])
        _render(ax, tiled)
        if i == 0:
            ax.set_title("exported 3×3×3 STL", pad=2, loc="center", fontweight="normal")
        # bands (search tier) with the claim and the guarded safe interval
        ax = fig.add_subplot(gs[i, 2])
        ev = next(x for x in s["calls"]["evaluate"]["result"]["results"] if x["design"] == d)
        b = ev["bands"]
        hz = b["hz_per_f_star"]
        f = np.array(b["f_star"]) * hz / 1e3
        cs = s["certificate_summary"]
        tg = s["calls"]["set_target"]["result"]["normalized"]
        gap_hz = [tg["gap"]["f_lo"] * hz, tg["gap"]["f_hi"] * hz] if "gap" in tg else None
        # the released rules (round 3, 2026-11-09) re-applied to the stored certificate: v14/engineering.json
        rs = next((x for x in J(RESCORE) if x["file"].startswith(f"{V6}/{sdir}/certificates/")
                   and x["kind"] == d["kind"] and x["params"] == d["params"]), None)
        assert rs is not None, sdir
        verdict = rs["after"]
        safe = rs["safe_interval_after"] if "gap" in tg else None
        why = rs.get("reason")
        L.add("F7", f"{title}.verdict_released_rules", verdict, RESCORE, "after (rescore_certificate)", script=S)
        # the filters: finer gap check under the released rules (counted n = 30, 40; edges at n = 60): v15
        fkey = next((k for k, c in J(FINE)["cells"].items() if c["source"].startswith(f"{V6}/{sdir}/")), None)
        fine = None if fkey is None else J(REJUDGE)["filters"][fkey]  # V15 solves, released rules (V19)
        if fine is not None:
            verdict, why = fine["after"], fine["gap_verdict"].get("reason")
            safe = fine["safe_interval"]
            L.add("F7", f"{title}.verdict_finer_gap_check", verdict, REJUDGE, f"filters.{fkey}.after", script=S)
        if safe and None in safe:
            safe = None
        top = 2.2 * gap_hz[1] / 1e3 if gap_hz else float(f.max())
        ymax = min(top, float(f.max()) * 1.02)
        if safe:
            ax.axhspan(safe[0] * hz / 1e3, min(safe[1] * hz / 1e3, ymax), color=GAP_SAFE, lw=0)
        if gap_hz:
            ax.axhspan(gap_hz[0] / 1e3, gap_hz[1] / 1e3, color=GAP_CLAIM, lw=0)
        ax.plot(np.arange(f.shape[0]), f, color="0.25", lw=0.6)
        ax.set_xticks([t[0] for t in b["k_ticks"]])
        ax.set_xticklabels([t[1].replace("G", "Γ") for t in b["k_ticks"]])
        ax.set_xlim(0, f.shape[0] - 1)
        ax.set_ylim(0, ymax)
        ax.set_ylabel("frequency (kHz)")
        if i == 0:
            ax.set_title("bands (search tier, n 10)", pad=2, loc="center", fontweight="normal")
        L.add("F7", f"{title}.bands", f"{f.shape[0]} k x {f.shape[1]} bands", sp,
              "calls.evaluate.result.results[released].bands.f_star x hz_per_f_star", status="derived", script=S)
        # evidence lines
        ax = fig.add_subplot(gs[i, 3])
        ax.set_axis_off()
        mat = s["config"]["material"]
        p = d["params"]
        lines = [(title, "b"), (f"{mat}, a = {s['config']['cell_size_mm']} mm", "k"),
                 (d["kind"].replace("_", " ") + " " + ", ".join(f"{k} {v:.3g}" for k, v in p.items()), "k"),
                 ((f"certificate, n 30/40/60: {verdict}" if fine is not None else f"certificate: {verdict}"
                   + ("" if verdict == cs["verdict"] else f" (was {cs['verdict']})")), "k")]
        if verdict != "certified" and why:
            why = ("no safe upper edge (drift to claim)" if "drift toward the claim" in why
                   else f"bars {why.split('spans ')[1].split(' voxels')[0]} voxels wide at n = 40"
                   if "voxels" in why else why)
            lines.append((why, OKABE["vermillion"]))
        if "E100_min" in tg:
            lines.append((f"E100 ≥ {cs['E100_MPa']:.1f} MPa (target {tg['E100_min'] * E_s / 1e6:.0f})", "k"))
            L.add("F7", f"{title}.E100_MPa", f"{cs['E100_MPa']:.1f}", sp, "certificate_summary.E100_MPa", unit="MPa",
                  script=S)
        if safe:
            lines.append((f"safe gap {safe[0] * hz / 1e3:.2f}–{safe[1] * hz / 1e3:.2f} kHz", "k"))
            L.add("F7", f"{title}.safe_gap_kHz", f"{safe[0] * hz / 1e3:.2f}-{safe[1] * hz / 1e3:.2f}",
                  REJUDGE if fine is not None else sp,
                  ("filters.*.safe_interval" if fine is not None
                   else "certificate_summary.gap.safe_interval") + " x hz_per_f_star", status="derived", unit="kHz",
                  script=S)
        r = J(f"{V6}/{rc}")
        rk = next((x for x in J(RECHECK) if x["file"] == f"{V6}/{rc}"), None)  # released rules (v14)
        rv = ("passed" if r["passed"] else "FAILED") if rk is None or not r["passed"] else \
            ("passed" if rk["after"] == "certified" else rk["after"])
        frc_path = {"case2/recheck_PA12.json": FINE_RC, "case2/recheck_316L.json": FINE_RC_316L}.get(rc)
        if frc_path and (ROOT / frc_path).exists():  # rechecked at the finer resolutions (v16)
            frc = J(frc_path)
            rv = "passed" if frc["overall"] == "certified" else frc["overall"]
            lines.append((f"STL recheck, n 30/40/60: {rv}", "k"))
            L.add("F7", f"{title}.stl_recheck", rv, frc_path, "overall (finer recheck, released rules)", script=S)
        else:
            lines.append((f"STL recheck, n 20/30/40: {rv}" if fine is not None else f"exported STL rechecked: {rv}",
                          "k"))
            L.add("F7", f"{title}.stl_recheck", rv, f"{V6}/{rc}; {RECHECK}", "passed, re-judged by the released rules",
                  script=S)
        sc = s["calls"]["screen_manufacturing"]["result"]
        mf = sc["min_feature"]
        flags = []
        if not cs["robust"]:
            flags.append("flag: not robust as built (±0.01 a)")
        if not sc["passed"]:
            flags.append(f"flag: fails screening ({mf['solid_est_mm']:.2f} < {mf['printer_limit_mm']:.1f} mm)")
        L.add("F7", f"{title}.robust", cs["robust"], sp, "certificate_summary.robust", script=S)
        L.add("F7", f"{title}.screen", sc["verdict"], sp, "calls.screen_manufacturing.result.verdict", script=S)
        lines += [(fl, OKABE["vermillion"]) for fl in flags]
        y = 0.97
        for t, c in lines:
            ax.text(0.0, y, t, va="top", ha="left", fontsize=8, color="k" if c == "b" else c,
                    transform=ax.transAxes, fontweight="normal" if c == "k" else "bold")
            y -= 0.135
    return style.save(fig, "F7_case_gallery", FIGURES)


# ============================================================================================================ F2
SHOTS = "paper/figures"
BAND_RGB = (32, 44, 64)   # colour of the caption band painted by scripts/verify/v6/gui_case_mount.py


def _load_shot(name):
    from PIL import Image
    a = np.asarray(Image.open(ROOT / SHOTS / name).convert("RGB"))
    top = 0
    while top < 120 and tuple(int(v) for v in a[top, 2]) == BAND_RGB:
        top += 1
    return a[top:], top


# regions of the certified-state screenshot (pixel boxes x0, y0, x1, y1 of the uncropped image, read from the
# image; the markers sit in the margins and point at the panel edges)
F2_REGIONS = [
    ("1", "specification: material, cell size, targets (stated and normalized)", (10, 95, 370, 545), "left"),
    ("2", "cell design: family, parameters, atlas suggestions", (10, 560, 370, 945), "left"),
    ("3", "export and manufacturing screening", (10, 960, 370, 1185), "left"),
    ("4", "cell preview", (380, 95, 1003, 470), "top"),
    ("5", "band diagram: claim and guarded safe interval", (380, 485, 1003, 900), "below"),
    ("6", "C*: search tier, certificate, guarded bounds", (1015, 95, 1665, 525), "right"),
    ("7", "full 6×6 tensor", (1015, 535, 1665, 870), "right"),
    ("8", "outcome card with the cited certificate", (1015, 890, 1665, 1540), "right"),
]


# value cell of the "certificate file" row of the outcome card (uncropped pixels, inclusive): an internal session
# path and file name, masked for the paper (confirm audit B7); the row label stays
F2_MASKS = [(1106, 1313, 1229, 1401)]


@sources(f"{SHOTS}/gui_case_mount_3_certified.png", f"{V6}/case1/gui_walkthrough.json")
def f2_gui(L: Ledger):
    _plt()
    img, top = _load_shot("gui_case_mount_3_certified.png")
    img = img.copy()
    for x0, y0, x1, y1 in F2_MASKS:  # fill with the card background; the text box only, row lines kept
        img[y0 - top:y1 - top + 1, x0:x1 + 1] = img[y1 - top - 3, x1 - 5].copy()  # blank corner of the same cell
    h, w = img.shape[:2]
    L.add("F2", "masked_px", str(F2_MASKS), f"{SHOTS}/gui_case_mount_3_certified.png",
          "certificate file path in the outcome card (internal session path) masked with the card background",
          status="derived", script=S)
    gw = J(f"{V6}/case1/gui_walkthrough.json")
    L.add("F2", "screenshot_px", f"{w}x{h} (top {top} px caption band cropped)", f"{SHOTS}/gui_case_mount_3_certified.png",
          "image size after crop", status="derived", script=S)
    L.add("F2", "gui_E100_MPa", f"{gw['checks']['certify']['E100_MPa']:.2f}", f"{V6}/case1/gui_walkthrough.json",
          "checks.certify.E100_MPa", unit="MPa", script=S)
    L.add("F2", "gui_verdict", gw["checks"]["certify"]["verdict"], f"{V6}/case1/gui_walkthrough.json",
          "checks.certify.verdict", script=S)
    margin = 0.045
    fw = DOUBLE
    img_w = fw * (1 - 2 * margin)
    fh = img_w * h / w + 4 * MM
    fig = plt.figure(figsize=(fw, fh))
    ax = fig.add_axes([margin, (2 * MM) / fh, 1 - 2 * margin, (img_w * h / w) / fh])
    ax.imshow(img, interpolation="lanczos")
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.set_axis_off()
    for lab, _, (x0, y0, x1, y1), side in F2_REGIONS:
        y0, y1 = y0 - top, y1 - top
        if side == "left":
            xy, xt = (x0, y0 + 12), (-55, y0 + 12)
        elif side == "right":
            xy, xt = (min(x1, w - 1), y0 + 12), (w + 55, y0 + 12)
        elif side == "top":
            xy, xt = ((x0 + x1) / 2, 0), ((x0 + x1) / 2, -45)  # ends at the image edge: no GUI pixel crossed
        else:
            xy, xt = ((x0 + x1) / 2, y1), ((x0 + x1) / 2, y1 + 60)
        ax.annotate(lab, xy=xy, xytext=xt, ha="center", va="center", fontsize=8, fontweight="bold",
                    annotation_clip=False,
                    bbox=dict(boxstyle="circle,pad=0.25", fc="white", ec=OKABE["vermillion"], lw=0.8),
                    arrowprops=dict(arrowstyle="-", color=OKABE["vermillion"], lw=0.8, shrinkA=0, shrinkB=0))
    return style.save(fig, "F2_gui_mount", FIGURES)


# (file, panel title, crop box in original pixels (x0, y0, x1, y1)); crops keep the GUI text legible at print size
F2S_SHOTS = [("gui_case_mount_1_spec.png", "specification and targets; bounds check: feasible", (10, 250, 372, 512)),
             ("gui_case_mount_2_evaluate.png", "atlas suggestions (search tier)", (10, 560, 372, 950)),
             ("gui_case_mount_4_export.png", "released, screened and exported", (10, 1176, 372, 1428)),
             ("gui_case_mount_4_export.png", "outcome card of the release", (1020, 905, 1670, 1085)),
             ("gui_live_certify_progress.png", "earlier live run: certificate in progress", (0, 36, 900, 76)),
             ("gui_live_refusal_rejected.png", "earlier live run: refusal without evidence rejected", (1024, 784, 1670, 862)),
             ("gui_live_proven_infeasible.png", "earlier live run: proven infeasible, citing a bound", (1026, 808, 1650, 905))]


# second and third line of the "printer limit" value in the export screenshot: a code identifier (the Python name of
# the material table) inside the GUI text, masked for the paper with the cell background (confirm audit 2, B2)
F2S_MASKS = {"gui_case_mount_4_export.png": [(124, 1376, 368, 1406)]}


@sources(*sorted({f"{SHOTS}/{s}" for s, _, _ in F2S_SHOTS}))
def f2s_gui_steps(L: Ledger):
    from PIL import Image
    _plt()
    fig = plt.figure(figsize=(DOUBLE, 215 * MM))
    gs = fig.add_gridspec(5, 2, height_ratios=[1.0, 0.62, 0.17, 0.17, 0.27], hspace=0.28, wspace=0.06)
    slots = [gs[0, 0], gs[0, 1], gs[1, 0], gs[1, 1], gs[2, :], gs[3, :], gs[4, :]]
    for i, ((name, cap, box), slot) in enumerate(zip(F2S_SHOTS, slots)):
        full = np.asarray(Image.open(ROOT / SHOTS / name).convert("RGB")).copy()
        for x0, y0, x1, y1 in F2S_MASKS.get(name, []):
            full[y0:y1 + 1, x0:x1 + 1] = 255
            L.add("F2s", f"{'abcdefg'[i]}.masked_px", str((x0, y0, x1, y1)), f"{SHOTS}/{name}",
                  "printer-limit source note (code identifier) masked with the white cell background", status="derived",
                  script=S)
        img = full[box[1]:box[3], box[0]:box[2]]
        ax = fig.add_subplot(slot)
        ax.imshow(img, interpolation="lanczos")
        ax.set_xticks([]), ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color("#999999"), sp.set_linewidth(0.5)
        ax.set_title(cap, fontsize=8, loc="left", pad=3)
        panel_label(ax, "abcdefg"[i], x=-0.012, y=1.02)
        L.add("F2s", f"{'abcdefg'[i]}.screenshot", name, f"{SHOTS}/{name}", f"crop {box} px", script=S)
    return style.save(fig, "F2s_gui_steps", FIGURES)


ALL = [f2_gui, f2s_gui_steps, f7_cases, f8_mount]
