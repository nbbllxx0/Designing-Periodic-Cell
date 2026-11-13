"""One figure style for every data figure of the paper (plan item A1).

Sizes: single column 85 mm, double column 175 mm (Elsevier). All text is 8 pt at print size (tick labels 8 pt
too); figures are drawn at their print width, so nothing is rescaled when placed. Colours: Okabe-Ito
(colour-blind safe). Output: PDF (vector, fonts embedded as Type 42) and PNG (300 dpi) in paper/figures/.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MM = 1 / 25.4
SINGLE = 85 * MM
DOUBLE = 175 * MM
FONT = 8.0

OKABE = dict(black="#000000", orange="#E69F00", sky="#56B4E9", green="#009E73", yellow="#F0E442",
             blue="#0072B2", vermillion="#D55E00", purple="#CC79A7", grey="#7F7F7F", lightgrey="#C8C8C8")

# fixed colours per family and per method / arm / outcome, so the same thing has the same colour in every figure
FAMILY = {"tpms": OKABE["blue"], "struts": OKABE["orange"], "resonator": OKABE["green"]}
METHOD = {"M1": OKABE["black"], "M2": OKABE["sky"], "M3": OKABE["purple"], "M4": OKABE["vermillion"],
          "M5": OKABE["orange"], "M6": OKABE["green"]}
OUTCOME = {"certified": OKABE["green"], "success": OKABE["green"], "correct_refusal": OKABE["blue"],
           "undetermined": OKABE["yellow"], "abstention": OKABE["yellow"], "refuted": OKABE["vermillion"],
           "false_refusal": OKABE["vermillion"], "search_tier_miss": OKABE["lightgrey"],
           "not_certified_search_tier_miss": OKABE["lightgrey"], "overclaim": OKABE["purple"],
           "no_answer": OKABE["grey"], "unsupported_release": OKABE["black"]}


def apply():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
        "font.size": FONT, "axes.titlesize": FONT, "axes.labelsize": FONT, "xtick.labelsize": FONT,
        "ytick.labelsize": FONT, "legend.fontsize": FONT, "legend.title_fontsize": FONT, "figure.titlesize": FONT,
        "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "xtick.minor.width": 0.4, "ytick.minor.width": 0.4, "xtick.major.size": 3, "ytick.major.size": 3,
        "xtick.minor.size": 1.8, "ytick.minor.size": 1.8, "xtick.direction": "out", "ytick.direction": "out",
        "axes.spines.top": False, "axes.spines.right": False,
        "lines.linewidth": 1.0, "lines.markersize": 3.5, "patch.linewidth": 0.5,
        "legend.frameon": False, "legend.handlelength": 1.4, "legend.borderaxespad": 0.3,
        "legend.labelspacing": 0.3, "legend.handletextpad": 0.4, "legend.columnspacing": 1.0,
        "axes.grid": False, "grid.linewidth": 0.4, "grid.color": "#DDDDDD",
        "savefig.dpi": 300, "figure.dpi": 150, "pdf.fonttype": 42, "ps.fonttype": 42,
        "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
        "axes.prop_cycle": matplotlib.cycler(color=[OKABE[c] for c in
                                                    ("blue", "orange", "green", "vermillion", "purple", "sky",
                                                     "black", "yellow")]),
    })


def figure(width=DOUBLE, height=70 * MM, **kw):
    apply()
    return plt.subplots(figsize=(width, height), **kw)


def panel_label(ax, s, x=-0.02, y=1.02):
    """Bold panel letter at the top left, outside the axes, plus nothing else (titles carry the text)."""
    ax.text(x, y, s, transform=ax.transAxes, fontsize=FONT, fontweight="bold", ha="right", va="bottom")


def save(fig, name: str, outdir) -> list:
    """Save <name>.pdf and <name>.png; returns the two paths."""
    outdir.mkdir(parents=True, exist_ok=True)
    fs = min_font_check(fig)
    assert fs >= FONT - 1e-9, f"{name}: text at {fs} pt is below the {FONT} pt minimum"
    paths = [outdir / f"{name}.pdf", outdir / f"{name}.png"]
    target_mm = fig.get_figwidth() * 25.4
    for p in paths:
        fig.savefig(p)
    plt.close(fig)
    # tight bounding boxes can grow a figure past its print width when a label sticks out; refuse that
    from PIL import Image
    with Image.open(paths[1]) as im:
        w_mm = im.size[0] / 300 * 25.4
    assert w_mm <= target_mm + 3.0, f"{name}: rendered width {w_mm:.0f} mm exceeds the {target_mm:.0f} mm target"
    return paths


def min_font_check(fig) -> float:
    """Smallest font size of any visible text artist in a figure (pt), for the 8 pt rule."""
    sizes = []
    for t in fig.findobj(matplotlib.text.Text):
        if t.get_visible() and t.get_text().strip():
            sizes.append(t.get_fontsize())
    return min(sizes) if sizes else FONT
