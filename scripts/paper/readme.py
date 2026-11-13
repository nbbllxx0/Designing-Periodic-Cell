"""paper/README.md: the one command and an index of every generated paper asset (plan item A1, batches 1 and 2)."""
from __future__ import annotations

import collections

from common import PAPER, ROOT, Ledger

TITLES = {
    "t2_contract": ("T2", "Tool contract: tools, inputs, outputs, interfaces"),
    "t3_checks": ("T3", "Acceptance checks per block, with thresholds and their assumptions"),
    "t4_verification": ("T4", "Verification summary (V1a registry/G2/published gap/one-sided, V1b two-sided, V1c "
                              "third party)"),
    "t5_search": ("T5", "Search benchmark (V3)"),
    "t6_performance": ("T6", "Performance (V4)"),
    "t8_agent": ("T8", "Agent evaluation (E4, amended A2), plus T8b outcomes per arm"),
    "t11_bounds": ("T11", "Bounds used for refusal, with their assumptions"),
    "t13_jobs": ("T13", "E4 job accounting, plus T13b frozen identity"),
    "t1_features": ("T1", "Feature comparison with existing tools; every cell cites its evidence entry "
                          "(T1_evidence.md, with the follow-up inspection's source URLs and read dates); cells not documented "
                          "in the inspected version marked unknown"),
    "t7_cases": ("T7", "Engineering cases (V6): mount design and reference, filters PA12 and 316L, with flags"),
    "t10_prior": ("T10", "Delta to the author's prior work (category (f) entries only)"),
    "t12_matrix": ("T12", "Capability and interface acceptance matrix (V2), failures by cause"),
    "t14_install": ("T14", "Installation and CI (B6 and B7 clean installs, B9 wheel, test suites, ci.yml)"),
    "t15_reproducibility": ("T15", "Reproducibility (V10 replay)"),
    "f3_stiffness": ("F3", "Stiffness verification: registry parity, V1b two-sided static, one-sided bounds, "
                           "cut-voxel bias and grid phase"),
    "f4_bandgap": ("F4", "Band-gap verification: published gap (Lucklum and Vellekoop 2018), certified gaps against "
                         "V1b/V1c references, edge margins"),
    "f5_search": ("F5", "Search benchmark: search-tier attainment curves, certified endpoints, outcome per method"),
    "f6_performance": ("F6", "Performance: throughput, tool latency, certificate time, scaling"),
    "f10_agent": ("F10", "Agent evaluation (A2): outcomes per arm, confirmatory tests"),
    "f11_atlas": ("F11", "Search atlas maps (stiffness-gap fronts) with certified cells marked"),
    "f2_gui": ("F2", "The GUI on the mount case after certification, regions 1-8 marked (screenshot unchanged)"),
    "f2s_gui_steps": ("F2s", "Supplement: GUI steps of the mount case and two refusal states from an earlier live run"),
    "f7_cases": ("F7", "Case gallery: exported STL, tiled block, bands with claim and safe interval, flags"),
    "f8_mount": ("F8", "Mount checks: stiffness, finite block vs homogenized, 6-cell transmission"),
    "f1_main_diagram": ("F1", "Tool overview (main diagram). Rendered file only; drawn by scripts/paper_private/ "
                          "(never published)"),
    "methods": ("Methods", "Equations, discretization, algorithms, thresholds with calibration sources, "
                           "file:function citations"),
    "supplement": ("Data", "Data dictionary of the result files likely to be released"),
    "guide": ("Guide", "Writing guide: venue and framing, outline, per-section notes with ledger ids, contributions, "
                       "limitations, objections, statements"),
    "captions": ("Captions", "Figure captions for F1, F2, F2s, F3-F8, F10, F11"),
    "failures": ("–", "Failure analysis: undetermined, refuted, marginal and refused cases (V1b, V1c, V2, V3, V6, E4)"),
}

BLOCKED = [
    ("F9", "GUI latency and modeled interaction cost", "V7 not run; V8 agent arm cut (mid-point review)"),
    ("F12", "Thermal", "B8 thermal cut for this paper"),
    ("T9", "Modeled interaction cost", "dropped with the V8 agent arm"),
]
T15 = ("T15", "Reproducibility", "waiting for V10: results/verification/v10/T15_v10.csv not present; built "
                                 "automatically by the next run once it exists")


def write(written: dict, L: Ledger):
    st = collections.Counter(r["status"] for r in L.rows)
    lines = ["# Paper assets (batch A1)", "",
             "Regenerate everything from the result files (no solver, GPU or LLM call; `amm` is not imported):", "",
             "```", "python scripts/paper/make_all.py", "```", "",
             "Options: `--only tables`, `--only figures`, `--only failures`, `--only docs` (the ledger and this "
             "README are written only by the full run). Scripts: `scripts/paper/` (`common.py` readers and ledger, "
             "`style.py` figure style, `tables.py` and `tables2.py`, `figures.py` and `figures2.py`, `failures.py`, "
             "`docs2.py`, `readme.py`, `make_all.py`).", "",
             "## Release rule: scripts/paper_private/ is never published", "",
             "`scripts/paper_private/` holds the script that draws the main diagram F1. By the author's rule the "
             "source of a main diagram is never released; only the rendered `paper/figures/F1_tool_overview.pdf|.png` "
             "is. Every release or packaging step must exclude `scripts/paper_private/`, and the release script (plan "
             "B7) must assert that no file from it is in the staged tree. `make_all.py` runs the private script when "
             "the folder is present and keeps the existing render otherwise. `scripts/paper/` holds data plots only: "
             "each figure function there declares the result files it plots, and the run fails if one declares none.",
             "",
             "## Index", "",
             "| Item | Content | Files |", "|---|---|---|"]
    for key, files in written.items():
        if key == "failures":
            continue
        tid, title = TITLES.get(key, (key, ""))
        lines.append(f"| {tid} | {title} | " + "<br>".join(f"`{f}`" for f in files) + " |")
    if "failures" in written:
        lines.append(f"| Failure analysis | {TITLES['failures'][1]} | `" + "`, `".join(written["failures"]) + "` |")
    lines.append("| Claims ledger | the numbers of the tables, figures, captions, failure analysis, methods and data "
                 "dictionary, and the result numbers of the writing guide (editorial numbers excluded), with source "
                 "file, field, generating script and status | "
                 "`results/claims_ledger.csv`, `results/claims_ledger.md` |")
    lines += ["", f"Ledger: {len(L.rows)} rows (" + ", ".join(f"{k} {v}" for k, v in sorted(st.items())) +
              f"); {len(L.conflicts)} conflicts between or inside result files, listed in the ledger's Conflicts "
              "section. A conflict is recorded with both values; none is resolved here.", "",
              "Figures are drawn at print width (85 mm or 175 mm) with 8 pt text; `style.save` refuses smaller "
              "text or a figure wider than its print width. Text inside the GUI screenshots (F2, F2s) is part of the "
              "image and prints at about 3 pt; the marked regions are explained in the caption. Captions: "
              "`paper/figures/CAPTIONS.md`.", "",
              "## Not produced", "", "| Item | Content | Reason |", "|---|---|---|"]
    blocked = list(BLOCKED)
    if "t15_reproducibility" not in written:
        blocked.append(T15)
    for a, b, c in blocked:
        lines.append(f"| {a} | {b} | {c} |")
    lines += ["", "Existing files kept as they are: `paper/figures/gui_*.png` (GUI screenshots used by F2 and F2s).",
              ""]
    p = PAPER / "README.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return [p]
