"""Week 3, E2: feasibility map from the atlas (search tier; values carry the calibrated error ranges in
results/atlas/error_model.json, so the map shows the attainable region, not certified values).

Panels: (a) E100 vs density with the Voigt bound and the isotropic Hashin-Shtrikman bound (reference only: the
cells are cubic); (b) G vs density with the Voigt bound; (c) widest relative gap vs E100, the stiffness-gap
trade-off; (d) gap mid-frequency f* = f a / c_t vs relative width.
Usage: plot_map.py [nu]  -> results/atlas/feasibility_map_nu<nu>.png / .pdf
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import amm  # noqa: F401
from amm import atlas, bounds

nu = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
rows = [r for r in atlas.load(f"results/atlas/atlas_nu{nu:g}.jsonl") if r.get("valid")]
FAM = {"tpms": ("TPMS", "#2a78d6", "o"), "struts": ("Strut lattices", "#eb6834", "^"),
       "resonator": ("Mass-in-frame resonators", "#1baf7a", "s")}
INK, MUTED, GRID = "#1f1f1e", "#6b6a63", "#e6e5e0"
plt.rcParams.update({"font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6})
fig, ax = plt.subplots(2, 2, figsize=(7.2, 6.4), layout="constrained")


def scatter(a, fam, x, y):
    lab, col, m = FAM[fam]
    a.scatter(x, y, s=10, c=col, marker=m, alpha=0.55, linewidths=0, label=lab,
              zorder={"tpms": 3, "struts": 2, "resonator": 1}[fam])


by = {f: [r for r in rows if r["spec"]["family"] == f] for f in FAM}
for f, rs in by.items():
    scatter(ax[0, 0], f, [r["density"] for r in rs], [r["E100"] for r in rs])
    scatter(ax[0, 1], f, [r["density"] for r in rs], [r["G"] for r in rs])
    g = [(r, atlas.row_gaps(r, min_rel=0.02)) for r in rs]
    g = [(r, gl[0]) for r, gl in g if gl]
    scatter(ax[1, 0], f, [r["E100"] for r, _ in g], [x["rel"] for _, x in g])
    scatter(ax[1, 1], f, [0.5 * (x["f_lo"] + x["f_hi"]) for _, x in g], [x["rel"] for _, x in g])

phi = np.linspace(0.02, 0.7, 200)
mu_s = bounds.solid_moduli(nu)["mu"]
ax[0, 0].plot(phi, phi, color=INK, lw=1.0, label="Voigt bound")
ax[0, 0].plot(phi, [bounds.hashin_shtrikman_porous(p, nu)["E"] for p in phi], color=INK, lw=1.0, ls="--",
              label="HS (isotropic, reference)")
ax[0, 1].plot(phi, phi * mu_s, color=INK, lw=1.0, label="Voigt bound")
for a in (ax[0, 0], ax[0, 1]):
    a.set_xscale("log"), a.set_yscale("log"), a.set_xlabel("Solid fraction")
ax[0, 0].set_ylabel("E100 / Es"), ax[0, 1].set_ylabel("G / Es")
ax[1, 0].set_xscale("log"), ax[1, 0].set_xlabel("E100 / Es"), ax[1, 0].set_ylabel("Widest relative gap")
ax[1, 1].set_xlabel("Gap mid-frequency f a / c_t"), ax[1, 1].set_ylabel("Relative gap width")
for a, t in zip(ax.flat, "abcd"):
    a.set_title(f"({t})", loc="left", fontsize=9, color=INK)
ax[0, 0].legend(frameon=False, fontsize=7, loc="upper left", handles=ax[0, 0].get_lines())
ax[0, 1].legend(frameon=False, fontsize=7, loc="upper left", handles=ax[0, 1].get_lines())
fig.legend(handles=ax[0, 0].collections, loc="outside lower center", ncol=3, frameon=False, fontsize=8,
           markerscale=1.6)
n = {f: len(v) for f, v in by.items()}
fig.suptitle(f"Family atlas, search tier (static n = 20, bands n = 10), nu_s = {nu:g}\n"
             + "valid cells: " + ", ".join(f"{FAM[f][0]} {n[f]}" for f in FAM), fontsize=8, color=MUTED)
for ext in ("png", "pdf"):
    fig.savefig(f"results/atlas/feasibility_map_nu{nu:g}.{ext}", dpi=220)
print("saved", n)
