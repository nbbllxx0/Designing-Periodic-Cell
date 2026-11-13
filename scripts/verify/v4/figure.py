"""V4 figure: fig_v4_performance.png, a data plot from the V4 result files (no diagram).

    python scripts/verify/v4/figure.py

Panels: (a) search-tier throughput vs batch size (warm median, min-max bar, cold marker) per family;
(b) tool latency through Session.call (median, range, cold marker); (c) certificate-time distribution by source
and target type (V3, V1b, E4, V4 fresh) with the static / Bloch split; (d) solve time vs n (static CPU, Bloch CPU
per factorization, Bloch GPU per k-point); (e) peak memory vs n; (f) MKL thread scaling.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

O = Path(__file__).resolve().parents[3] / "results" / "verification" / "v4"


def rd(name):
    with open(O / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def f(x):
    return None if x in (None, "", "None") else float(x)


def main():
    plt.rcParams.update({"font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "legend.fontsize": 7})
    fig, ax = plt.subplots(2, 3, figsize=(12.5, 7.4))
    cols = {"tpms": "#1b6ca8", "struts": "#d1495b", "resonator": "#2e933c"}

    # (a) throughput
    a = ax[0, 0]
    tp = [r for r in rd("throughput.csv") if r["mkl_threads"] == "16"]
    for fam in ("tpms", "struts", "resonator"):
        s = sorted([r for r in tp if r["family"] == fam], key=lambda r: int(r["batch"]))
        if not s:
            continue
        B = np.array([int(r["batch"]) for r in s])
        m = np.array([f(r["warm_cells_per_s_median"]) for r in s])
        lo = m - np.array([f(r["warm_cells_per_s_min"]) for r in s])
        hi = np.array([f(r["warm_cells_per_s_max"]) for r in s]) - m
        a.errorbar(B, m, yerr=[lo, hi], marker="o", ms=4, capsize=2, color=cols[fam], label=f"{s[0]['kind']} warm")
        a.plot(B, [f(r["cold_cells_per_s"]) for r in s], "x--", color=cols[fam], lw=0.8, label=f"{fam} cold")
    for r in rd("throughput.csv"):
        if r["mkl_threads"] == "4":
            a.plot(int(r["batch"]) * 1.12, f(r["warm_cells_per_s_median"]), "s", mfc="none", color=cols[r["family"]])
    a.set_xscale("log", base=2)
    a.set_xticks([1, 4, 16, 64], ["1", "4", "16", "64"])
    a.set_xlabel("batch size (cells per evaluate_batch call)")
    a.set_ylabel("cells / s")
    a.set_title("(a) search-tier throughput vs batch")
    a.set_ylim(0.3, 2.05)
    a.legend(ncol=2, frameon=False, loc="lower right", fontsize=6.5)
    a.text(0.02, 0.97, "open squares: 4 MKL threads, batch 16", transform=a.transAxes, va="top", fontsize=6.5)

    # (b) latency
    b = ax[0, 1]
    lat = [r for r in rd("latency.csv") if r["source"].startswith("V4")]
    lat = [r for r in lat if not r["tool"].startswith("set_")]  # spec setters take < 1 ms (sub-ms on a log axis)
    y = np.arange(len(lat))
    med = np.array([f(r["median_s"]) for r in lat])
    mn = np.array([f(r["min_s"]) for r in lat])
    mx = np.array([f(r["max_s"]) for r in lat])
    b.errorbar(med, y, xerr=[med - mn, mx - med], fmt="o", color="#333333", capsize=2, ms=4, label="median, range")
    b.plot([f(r["cold_s"]) for r in lat], y, "x", color="#d1495b", label="first call in process")
    b.set_yticks(y, [f"{r['tool']} (n={r['n_calls']})" for r in lat])
    b.invert_yaxis()
    b.set_xscale("log")
    b.set_xlabel("wall time per call (s)")
    b.set_title("(b) tool latency via Session.call")
    b.legend(frameon=False, loc="upper right")
    b.grid(axis="x", alpha=0.3, which="both")

    # (c) certificate times
    c = ax[0, 2]
    ct = rd("cert_times.csv")
    groups = []
    for src in ("V3", "V1b", "E4", "V4 fresh"):
        for tt in ("static", "gap", "combined"):
            v = [f(r["total_s"]) for r in ct if r["source"] == src and r["target_type"] == tt and f(r["total_s"])]
            if v:
                groups.append((f"{src} {tt} ({len(v)})", v, src))
    pos = np.arange(len(groups))
    c.boxplot([g[1] for g in groups], positions=pos, widths=0.55, showfliers=False)
    rng = np.random.default_rng(0)
    scol = {"V3": "#1b6ca8", "V1b": "#8f2d56", "E4": "#e09f3e", "V4 fresh": "#2e933c"}
    for p, (_, v, src) in zip(pos, groups):
        c.scatter(p + rng.uniform(-0.18, 0.18, len(v)), v, s=6, color=scol[src], alpha=0.7, zorder=3)
    c.set_xticks(pos, [g[0] for g in groups], fontsize=6, rotation=60, ha="right")
    c.set_yscale("log")
    c.set_ylabel("certificate wall time (s)")
    c.set_title("(c) certificate time (source, target type, n)")
    c.grid(axis="y", alpha=0.3, which="both")

    # (d) time vs n, (e) memory vs n
    sc = rd("scaling.csv")
    d, e = ax[1, 0], ax[1, 1]
    for path, lab, colr, mk in (("static", "static homogenization (CPU, 6 load cases)", "#1b6ca8", "o"),
                                ("bloch_cpu", "Bloch inertia count (CPU, 1 factorization)", "#d1495b", "s"),
                                ("bloch_gpu", "Bloch bands (GPU dense, 1 k-point)", "#2e933c", "^")):
        s = sorted([r for r in sc if r["path"] == path and r["mkl_threads"] == "16" and f(r["t_solve_s"])],
                   key=lambda r: int(r["n"]))
        if not s:
            continue
        n = [int(r["n"]) for r in s]
        d.plot(n, [f(r["t_solve_s"]) for r in s], marker=mk, color=colr, label=lab)
        if path == "bloch_cpu":
            d.plot(n, [f(r["t_edge_lanczos_s"]) for r in s], marker=mk, ls=":", color=colr, mfc="none",
                   label="Bloch Lanczos edge solve (CPU, 1 k)")
        memcol = "gpu_peak_alloc_mb" if path == "bloch_gpu" else "peak_wset_mb"
        e.plot(n, [f(r[memcol]) / 1024 for r in s], marker=mk, color=colr,
               label=lab.split(" (")[0] + (" (GPU allocated)" if path == "bloch_gpu" else " (process peak)"))
    for ax_ in (d, e):
        ax_.set_xscale("log")
        ax_.set_yscale("log")
        ax_.set_xticks([10, 16, 20, 24, 32, 40, 48, 64], ["10", "16", "20", "24", "32", "40", "48", "64"])
        ax_.minorticks_off()
        ax_.set_xlabel("resolution n (voxels per cell edge)")
        ax_.grid(alpha=0.3, which="both")
    d.set_ylabel("wall time (s)")
    d.set_title("(d) solve time vs resolution (cube_bars c 0.6, w 0.2)")
    d.legend(frameon=False, fontsize=6.5, loc="lower right")
    e.set_yticks([0.1, 0.2, 0.5, 1, 2, 5], ["0.1", "0.2", "0.5", "1", "2", "5"])
    e.set_ylabel("peak memory (GB)")
    e.set_title("(e) peak memory vs resolution")
    e.legend(frameon=False, fontsize=6.5)

    # (f) threads
    g = ax[1, 2]
    for path, n, lab, colr in (("static", "48", "static n = 48", "#1b6ca8"),
                               ("bloch_cpu", "30", "Bloch count n = 30", "#d1495b")):
        s = sorted([r for r in sc if r["path"] == path and r["n"] == n and f(r["t_solve_s"])],
                   key=lambda r: int(r["mkl_threads"]))
        if s:
            t = [int(r["mkl_threads"]) for r in s]
            g.plot(t, [f(r["t_solve_s"]) for r in s], "o-", color=colr, label=lab)
    g.set_xticks([4, 8, 16, 24])
    g.set_xlabel("MKL_NUM_THREADS = OMP_NUM_THREADS")
    g.set_ylabel("wall time (s)")
    g.set_title("(f) MKL thread scaling (i9-13900KF)")
    g.legend(frameon=False)
    g.grid(alpha=0.3)
    g.set_ylim(bottom=0)

    fig.tight_layout()
    fig.savefig(O / "fig_v4_performance.png", dpi=200)
    print("figure written")


if __name__ == "__main__":
    sys.exit(main())
