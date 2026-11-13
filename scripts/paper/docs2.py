"""Text assets of batch 2 (plan item A1): paper/METHODS.md, paper/SUPPLEMENT_data.md, paper/WRITING_GUIDE.md.

METHODS.md: governing equations, discretization and algorithms with file:function citations; every threshold and
guard factor is read from the amm source with `ast` (amm is never imported) and paired with its calibration source,
which is checked to exist in the named NOTES file.
SUPPLEMENT_data.md: data dictionary of the result files likely to be released; columns and keys are read from the
files themselves.
WRITING_GUIDE.md: framing, outline, per-section notes, contributions, delta, limitations, objections, cover letter,
highlights and statements. Every number in it is a value from the claims ledger, cited by its ledger id; the run fails
if an id is missing.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from common import PAPER, ROOT, Ledger, find_line, function_defaults, module_constants, read_json, read_text

S = "scripts/paper/docs2.py"


# ------------------------------------------------------------------------------------------------------- helpers
def _where(path: str, pattern: str) -> str:
    ln = find_line(path, pattern)
    assert ln, f"{pattern!r} not found in {path}"
    return f"{path}:{ln}"


def _has(path: str, text: str) -> str:
    """Assert that `text` occurs in `path` (calibration-source check); return 'path:line'."""
    t = read_text(path)
    i = t.find(text)
    assert i >= 0, f"calibration source text {text!r} not in {path}"
    return f"{path}:{t[:i].count(chr(10)) + 1}"


def _lv(L: Ledger, rid: str) -> str:
    for r in L.rows:
        if r["id"] == rid:
            return r["value"]
    raise KeyError(f"ledger id {rid!r} not found")


# ============================================================================================================ METHODS
def methods(L: Ledger):
    cf, bf, gf, hf, ff, af, uf, ef, sf, bdf, tf, evf = ("amm/certify.py", "amm/bloch.py", "amm/geometry.py",
                                                        "amm/homog.py", "amm/fem.py", "amm/atlas.py", "amm/units.py",
                                                        "amm/export.py", "amm/search.py", "amm/bounds.py",
                                                        "amm/tools.py", "amm/evaluate.py")
    cc, bc, gc, ec, tc = (module_constants(cf), module_constants(bf), module_constants(gf), module_constants(ef),
                          module_constants(tf))
    cd, bd, ad, ed, evd, sd, ffd = (function_defaults(cf), function_defaults(bf), function_defaults(af),
                                    function_defaults(ef), function_defaults(evf), function_defaults(sf),
                                    function_defaults(ff))
    em = read_json("results/atlas/error_model.json")
    box = module_constants(af)["BOX"][0]

    def C(mod, name, file):
        v, line, _ = mod[name]
        L.add("METHODS", name, str(v), file, f"{file}:{line}", script=S)
        return v, f"{file}:{line}"

    def D(d, fn, arg, file):
        v, line = d[fn][arg]
        L.add("METHODS", f"{fn}.{arg}", str(v), file, f"{file}:{line} (default of {fn})", script=S)
        return v, f"{file}:{line}"

    st_s, st_s_loc = C(cc, "STATIC_SAFETY", cf)
    st_p, st_p_loc = C(cc, "STATIC_P_MAX", cf)
    st_ph, st_ph_loc = C(cc, "STATIC_PHASES", cf)
    fcm, fcm_loc = C(cc, "FCM_ALPHA", cf)
    b_er, b_er_loc = C(cc, "BLOCH_EDGE_RES", cf)
    b_ph, b_ph_loc = C(cc, "BLOCH_PHASES", cf)
    g_s, g_s_loc = C(bc, "CONVERGENCE_SAFETY", bf)
    pmax, pmax_loc = C(bc, "P_MAX", bf)
    pmin, pmin_loc = C(bc, "P_MIN", bf)
    cmin, cmin_loc = C(gc, "C_MIN", gf)
    nfine, nfine_loc = C(gc, "N_FINE", gf)
    ftol, ftol_loc = C(ec, "FEATURE_TOL", ef)
    mx_eval, mx_eval_loc = C(tc, "MAX_EVAL", tf)
    mx_des, mx_des_loc = C(tc, "MAX_SESSION_DESIGNS", tf)
    mx_cert, mx_cert_loc = C(tc, "MAX_SESSION_CERTIFY", tf)
    ladder, ladder_loc = D(cd, "certify", "static_ladder", cf)
    tol_s, tol_s_loc = D(cd, "certify", "tol_static", cf)
    flat, flat_loc = D(cd, "static_convergence", "flat", cf)
    resb, resb_loc = D(cd, "certify", "res_bloch", cf)
    npath, npath_loc = D(cd, "certify", "n_path", cf)
    nint, nint_loc = D(cd, "certify", "n_interior", cf)
    adv_n, adv_n_loc = D(cd, "certify", "adversarial_n", cf)
    abo, abo_loc = D(cd, "certify", "as_built_offset", cf)
    adv_int, adv_int_loc = D(bd, "adversarial_ks", "n_interior", bf)
    adv_top, _ = D(bd, "adversarial_ks", "top", bf)
    adv_rounds, _ = D(bd, "adversarial_ks", "rounds", bf)
    adv_seed, _ = D(bd, "adversarial_ks", "seed", bf)
    adv_nev, _ = D(bd, "adversarial_ks", "nev", bf)
    ztol, ztol_loc = D(bd, "certify_gap", "zero_tol_f", bf)
    seed, _ = D(bd, "certify_gap", "seed", bf)
    ev_ns, ev_ns_loc = D(evd, "evaluate_batch", "n_static", evf)
    ev_nb, _ = D(evd, "evaluate_batch", "n_bloch", evf)
    ev_nf, _ = D(evd, "evaluate_batch", "n_fine", evf)
    sres, sres_loc = D(ed, "screen", "resolution", ef)
    stiles, _ = D(ed, "screen", "tiles", ef)
    sstep, sstep_loc = D(ed, "min_feature", "step", ef)
    n1, n1_loc = D(ad, "grid_specs", "n1", af)
    n2, _ = D(ad, "grid_specs", "n2", af)
    sbud, sbud_loc = D(sd, "search", "budget", sf)
    sq, _ = D(sd, "search", "q", sf)
    sarms, _ = D(sd, "search", "max_arms", sf)
    sncand, _ = D(sd, "search", "n_cand", sf)
    sobj, _ = D(sd, "search", "objective", sf)
    st_tier = re.search(r"SEARCH_TIER = dict\((.*?)\)", read_text(af)).group(1)
    L.add("METHODS", "SEARCH_TIER", st_tier, af, _where(af, r"^SEARCH_TIER = "), script=S)
    tool_budget = re.search(r"def search\(self, budget: int = (\d+)", read_text(tf)).group(1)
    L.add("METHODS", "Session.search.budget", tool_budget, tf, _where(tf, r"def search\(self, budget"), script=S)
    for k in ("safety", "n_cells"):
        L.add("METHODS", f"error_model.{k}", em[k], "results/atlas/error_model.json", k, script=S)
    L.add("METHODS", "error_model.domain", json.dumps(em["domain"]), "results/atlas/error_model.json", "domain",
          script=S)
    L.add("METHODS", "error_model.thin_below", json.dumps(em["thin_below"]), "results/atlas/error_model.json",
          "thin_below", script=S)

    # calibration sources (text must exist in the named file)
    g2 = "results/g2/NOTES.md"
    cal = {
        "STATIC_SAFETY": _has(g2, "lower = min(all values, ext - 2 err), upper = max(all values, ext + 2 err)"),
        "STATIC_P_MAX": _has(g2, "A p cap of 2 was also rejected"),
        "phases": _has(g2, "With 3 phases instead of 5"),
        "held_out": _has(g2, "11 cells **not** among the 50"),
        "P_MAX": _has(g2, "has **no held-out calibration**"),
        "gap_safety": _has("results/verification/NOTES.md", "The safety factor of 2 is **calibrated on this one case**"),
        "error_model": _has("results/atlas/NOTES.md", "e in [0, 1.25 × max seen]"),
        "error_cells": _has("results/atlas/NOTES.md", "73 cells in total"),
        "gap_ranges": _has("results/atlas/NOTES.md", "The gap ranges are wide and rest on few cells"),
        "fcm": _has(g2, "FCM") if "FCM" in read_text(g2) else None,
    }
    for k, v in cal.items():
        if v:
            L.add("METHODS", f"calibration_source.{k}", v, v.split(":")[0], "text located", status="verified",
                  script=S)
    # the held-out calibration population of the static guard (final asset audit, finding 10)
    m_cal = re.search(r"Calibration data: `scripts/g2/phase_ladder\.py`, (\d+) cells \*\*not\*\* among the (\d+)",
                      read_text(g2))
    assert m_cal, "calibration population not found in results/g2/NOTES.md"
    n_cal, n_g2 = int(m_cal.group(1)), int(m_cal.group(2))
    L.add("METHODS", "static_guard.calibration_cells", n_cal, g2, f"text at {cal['held_out']}: held-out cells of the "
          "phase-ladder study (not among the G2 cells)", script=S)
    L.add("METHODS", "static_guard.g2_cells", n_g2, g2, f"text at {cal['held_out']}", script=S)

    tpl = lambda t: "(" + ", ".join(str(x) for x in t) + ")"
    lad_txt = " → ".join(tpl(r) for r in ladder)
    M = []
    M += ["# Methods reference (amm 0.2.0, tool contract amm-tools/3)", "",
          "Generated by `scripts/paper/docs2.py` (run `scripts/paper/make_all.py`). Every constant below is read from "
          "the amm source text (`ast`; amm is not imported) and every calibration source is checked to exist in the "
          "file named; the values are in `results/claims_ledger.csv` (asset METHODS). Citations are `file:line` or "
          "`file:function`. What a certificate does and does not guarantee: section 9.", ""]

    M += ["## 1. Units and normalization", "",
          f"The solvers work with E_s = 1, ρ_s = 1 and cell edge a = 1 (`{uf}:normalize`, `{uf}:c_t`). Stiffness is "
          "reported as a fraction of E_s; frequency as f* = f a / c_t with the solid shear-wave speed",
          "", "    c_t = sqrt( E_s / (2 (1 + ν_s)) / ρ_s ).", "",
          "A physical request (Pa…GPa, Hz…MHz, mm…m) is converted with the material's E_s, ν_s, ρ_s and the cell size. A "
          "stiffness in pressure units without a material, or a frequency in Hz without a cell size, cannot be "
          f"normalized and is reported as missing (UNDERSPECIFIED / need_info), not guessed (`{uf}:normalize`). Built-in "
          f"materials: `{uf}:MATERIALS` (typical datasheet values, inputs of a request, not claims).", ""]

    M += ["## 2. Geometry and voxelization", "",
          f"Three cubic-symmetric families, each a level-set field φ with solid where φ ≤ threshold (`{gf}:field`):",
          "- **tpms**: gyroid, Schwarz P, diamond, IWP (`tpms_field`), network (φ = f) or sheet (φ = |f|), set by a "
          "target solid fraction (the threshold is found by bisection on the anti-aliased volume, `_fine_coverage`);",
          "- **struts**: sc, bcc, octet; distance to the strut segments minus r, optional node spheres R "
          "(`_segments`, `_nodes`, `_dist_to_segments`);",
          "- **resonator**: cube_bars (core cube edge c, square bars width w; `_box`), sphere_ligaments (core radius c, "
          "round bars diameter w).", "",
          f"Parameter boxes (fractions of a): {', '.join(f'{k} {v}' for k, v in box.items())} (`{af}:BOX`); validity "
          f"rules in `{af}:valid` (cube_bars w ≤ c − 0.04; sphere_ligaments w ≤ 2c − 0.02; strut node sphere absent or "
          "R ≥ r + 0.03).", "",
          f"**Voxelization** (`{gf}:_fine_coverage`, `voxelize`, `design_cell`): each voxel gets s³ sub-samples with "
          f"n s ≥ N_FINE = {nfine} ({nfine_loc}); s = max(2, ⌈N_FINE / n⌉) (`supersample`). A sub-sample's solid "
          "fraction is 0.5 − d/δ clipped to [0, 1], with d the approximate signed distance (φ − t)/|∇φ| and δ the "
          "sub-sample width (`_soft`, `_signed_distance`; exact for planes). Voxel coverage is the sub-sample mean; "
          f"voxels below C_MIN = {cmin} are void ({cmin_loc}). `clean` keeps the largest periodically "
          "face-connected component (by solid volume) and reports the removed fraction and percolation in x, y, z "
          "(`clean`, `periodic_labels`, `percolates`). A **grid phase** translates the design by a fraction of a voxel "
          "before voxelizing (`design_cell(phase=...)`); the cell is periodic, so differences between phases are pure "
          "discretization error.", ""]

    M += ["## 3. Finite elements", "",
          f"Voxel hexahedra on the periodic node set (`{ff}:build_mesh`, `CellMesh`). Full voxels use 8-node elements with "
          f"9 Wilson-Taylor incompatible bubble modes, statically condensed, 2×2×2 Gauss (`{ff}:hex8_ke`, element "
          f"\"hex8i\"); this passes the patch test on cubes. Partial voxels use finite-cell integration: B^T D B and "
          f"N^T ρ N are integrated over the element's own solid sub-samples with the midpoint rule (`{ff}:fcm_tables`). "
          f"Mass matrices are consistent (`{ff}:hex8_me`). The isotropic solid: `{ff}:elastic_D` (Lamé form, "
          f"engineering shear strains yz, xz, xy). On a factorization failure the static solve is retried with a stiffness "
          f"floor α K_full on partial voxels, α = FCM_ALPHA = {fcm} ({fcm_loc}).", ""]

    M += ["## 4. Static homogenization", "",
          "Find, for each of the six unit macroscopic strains ε⁰_m, a Y-periodic fluctuation χ_m with", "",
          "    ∫_Y ε(v) : C_s : ( ε⁰_m − ε(χ_m) ) dY = 0   for every Y-periodic v,", "",
          "and set", "",
          "    C*_mn = (1/|Y|) ∫_Y ( ε⁰_m − ε(χ_m) ) : C_s : ( ε⁰_n − ε(χ_n) ) dY ,   |Y| = 1.", "",
          f"Discrete form (`{hf}:homogenize`): K χ_m = F_m with F_m from the element affine fields χ⁰_m = x·ε⁰_m; the three "
          "rigid translations are removed by pinning node 0 (the cell must be one connected periodic component); one "
          "FP64 sparse Cholesky factorization (PARDISO, mtype 2) for the six right-hand sides; then "
          "C*_mn = Σ_e (χ⁰_m − χ_m)_eᵀ k_e (χ⁰_n − χ_n)_e. Recorded per solve: relative residual of each load case, "
          "‖C − Cᵀ‖/‖C‖ and the smallest eigenvalue of C*.", "",
          f"Engineering constants (`{hf}:cubic_constants`): C11, C12, C44 as cubic averages; S = C*⁻¹; E100 = 1/S11; "
          "ν100 = −S12/S11; G = C44; bulk = (C11 + 2 C12)/3; Zener = 2 C44/(C11 − C12); cubic deviation = ‖C − C_cubic‖/‖C‖. "
          "Targets may be set on density, E100, G, bulk and ν100 only; Zener, E110, E111 and the Voigt/Reuss averages "
          f"are outputs (`{tf}:OUTPUT_QUANTITIES`).", ""]

    M += ["## 5. Bloch eigenproblem (3D, complete gaps)", "",
          "Bloch waves u(x) = ũ(x) e^{i k·x} with Y-periodic ũ satisfy, for every periodic v,", "",
          "    ∫_Y ε_k(v)* : C_s : ε_k(ũ) dY = ω² ∫_Y ρ v*·ũ dY ,   ε_k(ũ) = sym( ∇ũ + i k ⊗ ũ ),", "",
          f"discretized as the Hermitian pencil K(k) U = ω² M(k) U. The phase e^{{i k·w}} is applied to element nodes "
          f"that wrap across a cell face (`{ff}:CellMesh._phases`, `element_values`); f* = ω / (2π c_t) "
          f"(`{bf}:f_to_sigma`). k is sampled on the simple-cubic irreducible zone: path Γ-X-M-Γ-R-X (`{bf}:kpath`, "
          f"`SC_PATH`) and uniform random points in 0 ≤ k_z ≤ k_y ≤ k_x ≤ π (`{bf}:ibz_interior`). Cubic point symmetry of "
          f"the cell is assumed (`{bf}:to_ibz`). A complete gap between bands j and j+1 is [max_k f_j, min_k f_(j+1)] "
          f"over the sampled k (`{bf}:gaps`).", "",
          f"**Search tier** (`{bf}:GPUBands`): dense generalized Hermitian eigenproblems batched over k on the GPU in "
          "complex64 (Cholesky of M, L⁻¹ K L⁻ᴴ, eigvalsh), with deterministic assembly (a fixed-order gather instead of "
          "atomic adds) so that sessions replay exactly; CPU fallback when no CUDA device exists (not bit-identical).", "",
          f"**Certificate tier: inertia counts** (`{bf}:InertiaCounter.counts`). For a shift σ = (2π c_t f)², K(k) − σ M(k) "
          "is factored in FP64 as LDLᵀ on its real 2N form (PARDISO, mtype −2). By Sylvester's law of inertia, the number "
          "of negative pivots equals twice the number of Bloch eigenvalues below σ. A claim [f_lo, f_hi] above band j "
          f"holds at a k exactly when count(f_lo) = count(f_hi) = j. Checks (`{bf}:certify_gap`): at Γ exactly 3 "
          f"eigenvalues below f* = {ztol} ({ztol_loc}; a non-percolating cell fails); equal counts at every sampled k; "
          "no perturbed pivots and even raw counts. Counts are exact statements about the discretized model at the "
          "sampled k; they say nothing about unsampled k.", "",
          f"**Adversarial k** (`{bf}:adversarial_ks`): on a coarse mesh (n = {adv_n}, {adv_n_loc}) the GPU search tier "
          f"evaluates the path plus {adv_int} random interior points (seed {adv_seed}, nev {adv_nev}), then a pattern "
          f"search (26 directions, step 0.15π halved each round, {adv_rounds} rounds) from the {adv_top} best starts of "
          "each bounding band; the k found are added to the certificate's count set.", "",
          f"**Edge estimates** (`{bf}:InertiaCounter.edge`, `_extreme_edge`): shift-invert Lanczos (ARPACK, tol 1e-7, "
          "fixed start vector for exact replay) at the symmetry points or the previous resolution's extreme k; every other "
          "k is screened by one inertia count at the current edge ± 1e-6 (relative) and solved only if it is more "
          "extreme.", ""]

    M += ["## 6. Acceptance tier: certificate blocks and guards", "",
          f"`{cf}:certify` runs the blocks below; `{tf}` exposes it as the `certify` tool (profile C only).", "",
          "### 6.1 Static block (`static_block`, `static_convergence`, `static_verdict`)", "",
          f"- Ladder {lad_txt} ({ladder_loc}); every resolution is solved at grid phases 0 and "
          f"{', '.join(map(str, st_ph))} voxel ({st_ph_loc}).",
          "- Per quantity: phase means m(n₁), m(n₂), m(n₃), h = 1/n. If m is monotone with a shrinking step, the order p "
          f"is fitted through the three means (`{bf}:_order`, p ∈ [{pmin}, 8]) and capped at STATIC_P_MAX = {st_p} "
          f"({st_p_loc}); with r = h₃^p / (h₂^p − h₃^p): ext = m₃ + (m₃ − m₂) r, remaining error e = |m₃ − m₂| r. "
          f"Otherwise, if every change is below `flat` = {flat} ({flat_loc}) or within the phase noise "
          "(|Δ| ≤ s·P, P = phase spread at n₃): ext = m₃, e = max(|m₃ − m₂|, P). Else: not converged.",
          f"- Converged when e and P are ≤ tol_static = {tol_s} ({tol_s_loc}; relative, absolute for ν100). Guarded "
          f"bounds: lower = min(all computed values, ext − s e), upper = max(all values, ext + s e), s = STATIC_SAFETY = "
          f"{st_s} ({st_s_loc}).",
          "- A rung is used when every targeted quantity has converged and every target is met by the guarded bound; "
          "otherwise the next rung is tried.",
          "- Numerical checks per solve (`_static_row`): residual ≤ 1e-10 for all six load cases; asymmetry ≤ 1e-10; "
          "min eigenvalue of C* > 1e-8; no perturbed pivots; solid removed as islands ≤ 0.01; percolation in x, y, z.",
          "- Verdict per target: certified (guarded bound clears it, quantity converged); refuted (the opposite guarded "
          "bound misses it; for a minimum on E100, G or bulk the largest computed value suffices because these converge "
          f"from above, `FROM_ABOVE`); else undetermined. Invalid geometry (empty, not percolating, > 1 % islands) "
          "refutes; a solver failure is undetermined.", "",
          "### 6.2 Bloch block (`bloch_block`, `gap_convergence`, `gap_verdict`)", "",
          f"- Counted resolutions n = {', '.join(map(str, resb))} ({resb_loc}); path with {npath} points per leg "
          f"({npath_loc}) plus {nint} random interior k ({nint_loc}, seed {seed}) plus the adversarial k.",
          f"- Edge-only third resolution n = {', '.join(map(str, b_er))} ({b_er_loc}): Lanczos at the two most extreme k "
          f"of the finest counted resolution; grid phases {', '.join(map(str, b_ph))} at the finest counted resolution "
          f"({b_ph_loc}).",
          f"- Edge guard (`{bf}:_edge_guard`): order p fitted per edge through the three resolutions, capped at P_MAX = "
          f"{pmax} ({pmax_loc}); slower than P_MIN = {pmin} ({pmin_loc}) or non-monotone beyond the phase noise fails "
          "closed. ext = f₃ + d₂₃ r, err = |d₂₃| r; the safe lower edge is the maximum of all computed edges, the phase "
          f"edges and ext + s·err (upper edge: minimum, ext − s·err), s = CONVERGENCE_SAFETY = {g_s} ({g_s_loc}). The "
          "claim must lie inside the safe interval.",
          "- Densities of the counted resolutions must agree within 0.01 (`bloch_block`).",
          "- Verdict: certified if counts and edge guard pass; refuted if a guarded edge bound excludes the claim; "
          "otherwise undetermined (a count failure is an abstention: edges converge from above, so a mode inside the "
          "claim on a finite mesh does not prove the converged gap closed).", "",
          "### 6.3 As-built flag (`as_built_block`)", "",
          f"The surface is eroded and dilated by {abo} a ({abo_loc}) as a shift of the signed distance; static targets "
          "(densities excluded) are re-checked by one solve at the first resolution of the rung used, and the gap "
          "counts at n = 20 on 2 path points per leg and 4 interior k. A failure sets `robust` = false; it is a flag, "
          "not required for release.", "",
          "### 6.4 Bounds used for refusal (`" + bdf + ":check`)", "",
          "- V1 (Voigt, any geometry): C* ≤ φ C_s, so E(n) ≤ φ E_s, C44 ≤ φ μ_s, bulk ≤ φ K_s with φ = density_max.",
          "- S1 (stability, cubic design space): ν100 ∈ (−1, 1/2).",
          "- P1 (consistency): a minimum above its maximum, E100_max ≤ 0, solid fraction outside (0, 1].",
          "- W1: a complete gap cannot contain f = 0; f_hi > f_lo.",
          "- Hashin-Shtrikman upper bounds (porous): advisory for cubic requests, rigorous only for isotropic ones "
          "(`hashin_shtrikman_porous`). Table T11 lists the bounds with their assumptions.", ""]

    M += ["## 7. Search tier, atlas and search", "",
          f"- `evaluate` (`{evf}:evaluate_batch`, defaults n_static {ev_ns}, n_bloch {ev_nb}, one shared sub-sample grid "
          f"n_fine {ev_nf}; the tools use `{af}:SEARCH_TIER` = dict({st_tier})): static homogenization on the CPU and the "
          "band diagram on the k-path on the GPU, finite-cell partial voxels. Results are labelled search tier.",
          f"- Atlas (`{af}:grid_specs`, n1 = {n1} densities per TPMS kind and mode, n2 = {n2} per 2-D axis, validity "
          f"rules applied; `{af}:run`): one search-tier row per cell, band diagram kept, at ν_s = 0.3, 0.342, 0.39.",
          "- Error model (`results/atlas/error_model.json`, `" + af + ":error_model`, `err_for`): true = search / (1 + e) "
          f"with e in calibrated one-sided ranges per family and quantity; gap edges: true = search − e f_mid; thin "
          f"cells (feature parameter below {json.dumps(em['thin_below'])}) use wider ranges; calibrated domain "
          f"{json.dumps(em['domain'])}; range ends include a factor {em['safety']} on the largest error seen, from "
          f"{em['n_cells']} reference cells.",
          f"- Slack (`{af}:slacks`): per target, (q − t)/|t| for a minimum, (t − q)/|t| for a maximum; for a gap, the best "
          "over the cell's gaps of min(f_lo − e_lo, e_hi − f_hi)/f_mid; overall slack = minimum. Cases: nominal, "
          "expected (median error), pessimistic, optimistic.",
          f"- Atlas verdict (`{af}:oracle`): FEASIBLE if some calibrated cell clears every target at the pessimistic end; "
          "NOT_FOUND_IN_FAMILIES if every cell misses at the optimistic end and so does the bilinear interpolation "
          "between grid cells (`interpolated_best`); BORDERLINE otherwise. Interpolation is an estimate, not a bound.",
          f"- `search` (`{sf}:search`): Bayesian optimization per arm (kind, TPMS mode) with a SingleTaskGP and qLogEI "
          f"over a Sobol candidate set (n_cand {sncand}), batch q = {sq}, objective \"{sobj}\" (median-corrected slack), "
          f"atlas rows as free seed data choosing the {sarms} best arms; library default budget {sbud} ({sbud_loc}); "
          f"the `search` tool defaults to {tool_budget} and accepts 8-96 (`{tf}:Session.search`).", ""]

    M += ["## 8. Export, screening and session limits", "",
          f"- Export (`{ef}:build`, `surface`): marching cubes of the level-set field (resolution 64 per cell edge for the "
          "cell, 32 per cell for the tiled block by default), welded, checked watertight (`mesh_check`); STL in mm; "
          "report.json carries the outcome, the certificate reference and the disclaimers (`REPORT_DISCLAIMERS`).",
          f"- Screening (`{ef}:screen`, resolution {sres}, tiles {stiles}): minimum solid and void feature by "
          f"morphological opening with a ball, bisection to {sstep} voxel (`min_feature`, {sstep_loc}); a phase fails "
          f"when more than FEATURE_TOL = {ftol} of it is thinner than the printer limit ({ftol_loc}); tiled "
          "connectivity of the block; watertight surfaces. Screening only, not a printability claim; the estimate is "
          "conservative by about 1-2 voxels.",
          f"- Session limits (`{tf}`): at most {mx_eval} designs per evaluate call ({mx_eval_loc}), {mx_des} designs "
          f"and {mx_cert} certificates per session ({mx_des_loc}, {mx_cert_loc}).",
          "- Reproducibility: `import amm` sets MKL_CBWR=AUTO,STRICT and MKL_NUM_THREADS=16 (`amm/_runtime.py`); a "
          "session log replays bit-exactly on the machine and code that wrote it (`amm/tools.py:replay`).", ""]

    rows = [
        ("STATIC_SAFETY", st_s, st_s_loc, "static guard factor on the remaining error",
         f"held-out phase-ladder study on {n_cal} cells not among the {n_g2} G2 cells ({cal['held_out']}); guard "
         f"defined at "
         f"{cal['STATIC_SAFETY']}"),
        ("STATIC_P_MAX", st_p, st_p_loc, "cap on the fitted static convergence order",
         f"same study; a cap of 2 was rejected ({cal['STATIC_P_MAX']})"),
        ("STATIC_PHASES", "0, " + ", ".join(map(str, st_ph)), st_ph_loc, "grid phases per resolution (voxel widths)",
         f"same study; 3 phases rejected ({cal['phases']})"),
        ("tol_static", tol_s, tol_s_loc, "convergence tolerance (remaining error and phase spread)",
         "design choice stated with the guard (results/g2/NOTES.md 8.2); no separate calibration recorded"),
        ("flat", flat, flat_loc, "changes treated as converged noise", "design choice; no calibration recorded"),
        ("static numerics", "residual ≤ 1e-10, asymmetry ≤ 1e-10, min eig > 1e-8, islands ≤ 0.01", f"{cf}:_static_row",
         "per-solve checks", "design choice; no calibration recorded"),
        ("FCM_ALPHA", fcm, fcm_loc, "finite-cell stiffness floor on retry",
         f"added as a retry after one singular G2 cell; changes a healthy solve by < 1e-8 relative "
         f"({_has(g2, 'the finite-cell stiffness floor')}); no calibration beyond this check"),
        ("CONVERGENCE_SAFETY", g_s, g_s_loc, "gap-edge guard factor",
         f"calibrated on one published case, Lucklum and Vellekoop (2018) ({cal['gap_safety']}); empirical"),
        ("P_MAX (gap)", pmax, pmax_loc, "cap on the fitted edge order",
         f"no held-out calibration ({cal['P_MAX']})"),
        ("P_MIN", pmin, pmin_loc, "slowest order the edge guard fits (else fails closed)",
         "design choice; no calibration recorded"),
        ("res_bloch / BLOCH_EDGE_RES / BLOCH_PHASES", f"{resb} / {b_er} / {b_ph}", f"{resb_loc}; {b_er_loc}; {b_ph_loc}",
         "Bloch resolutions and phases", "results/g2/NOTES.md section 8.3 (gap guard design); not calibrated on "
                                         "held-out cells"),
        ("zero_tol_f", ztol, ztol_loc, "Γ check: 3 modes below this f*", "design choice; no calibration recorded"),
        ("adversarial k", f"n {adv_n}, {adv_int} interior, top {adv_top}, {adv_rounds} rounds", adv_n_loc,
         "interior-k search", "mutation test with an injected band bump (results/g2/NOTES.md 8.4); not a guarantee"),
        ("as_built_offset", abo, abo_loc, "erosion/dilation for the robustness flag",
         "design choice; no calibration recorded"),
        ("C_MIN", cmin, cmin_loc, "void floor of voxel coverage", "source comment: near-empty elements make K − sM "
                                                                     "near-singular; no calibration recorded"),
        ("error model", f"safety {em['safety']}, {em['n_cells']} cells", "results/atlas/error_model.json",
         "search-tier error ranges", f"{cal['error_model']}; {cal['error_cells']}; gap ranges rest on few cells "
                                     f"({cal['gap_ranges']})"),
        ("FEATURE_TOL", ftol, ftol_loc, "screening tolerance", "design choice; no calibration recorded"),
    ]
    M += ["## 9. Thresholds and guard factors with their calibration sources", "",
          "| constant | value | where | role | calibration source |", "|---|---|---|---|---|"]
    for name, v, loc, role, src in rows:
        M.append(f"| {name} | {v} | `{loc}` | {role} | {src} |")
    M += ["", "**What these settings mean.** The certificate is acceptance under stated discretization, sampling and "
              "guard assumptions, not a continuum theorem: guard bands come from fitted convergence orders and sampled "
              "grid phases, not from a-priori error bounds; a band could enter the gap between sampled k; the gap is "
              "for the infinite periodic lattice. Factors marked 'no calibration recorded' are design choices and "
              "should be stated as such in the paper (docs/concepts.md, 'What a certificate guarantees').", ""]
    p = PAPER / "METHODS.md"
    p.write_text("\n".join(M), encoding="utf-8")
    return [p]


# ============================================================================================================ DATA
# Units per data file and column (final asset audit, finding 6: no inference from the column-name suffix). A column
# not listed has no unit: a count, flag, label, identifier, normalized quantity (stiffness / E_s, f* = f a / c_t,
# lengths / a) or a dimensionless ratio, as the description says. `_UNIT_LIKE` is a guard, not an inference: a column
# whose name looks unit-bearing must be listed, so a new column cannot silently print without its unit.
_S, _MB = "s", "MB"
UNITS = {
    "results/verification/registry_rows.csv": {"seconds": _S},
    "results/verification/v1b/T4_v1b.csv": {},
    "results/verification/dolfinx/summary.csv": {},
    "results/verification/v14/bench/runs.csv": {
        "search_seconds": _S, "evaluator_seconds": _S, "throughput_evals_per_s": "evaluations/s",
        "cert_seconds": _S, "workflow_seconds": _S, "evals_spent": "evaluations", "evals_to_final": "evaluations"},
    "results/verification/v14/bench/T5_v3.csv": {
        "throughput_evals_per_s": "evaluations/s", "latency_search_s_median": _S, "cert_s_median_when_called": _S,
        "workflow_s_median": _S, "workflow_s_total": _S, "evals_spent_mean": "evaluations",
        "evals_to_final_mean": "evaluations", "cost_C_mean": "evaluations"},
    "results/verification/v4/throughput.csv": {
        "import_s": _S, "cold_wall_s": _S, "cold_cells_per_s": "cells/s", "warm_cells_per_s_median": "cells/s",
        "warm_cells_per_s_min": "cells/s", "warm_cells_per_s_max": "cells/s", "warm_s_per_cell_median": "s/cell",
        "warm_same_specs_cells_per_s": "cells/s", "warm_static_s_per_cell": "s/cell",
        "warm_bloch_s_per_cell": "s/cell", "gpu_peak_alloc_mb": _MB, "gpu_peak_reserved_mb": _MB,
        "process_peak_wset_mb": _MB},
    "results/verification/v4/latency.csv": {
        "cold_s": _S, "median_s": _S, "min_s": _S, "max_s": _S, "p25_s": _S, "p75_s": _S, "warm_median_s": _S,
        "warm_min_s": _S, "warm_max_s": _S, "per_call_s": "s (space-separated list, one per call)"},
    "results/verification/v4/cert_times.csv": {"total_s": _S, "static_s": _S, "bloch_s": _S, "as_built_s": _S},
    "results/verification/v4/scaling.csv": {
        "t_geometry_s": _S, "t_mesh_s": _S, "t_solve_s": _S, "t_solve_reps_s": "s (list of repeats)",
        "t_assemble_s": _S, "t_factor_s": _S, "t_solve6_s": _S, "t_count_first_s": _S, "t_edge_lanczos_s": _S,
        "t_setup_s": _S, "t_1k_cold_s": _S, "t_path21_s": _S, "peak_wset_mb": _MB, "mem_before_solve_mb": _MB,
        "gpu_peak_alloc_mb": _MB, "dense_per_k_gb": "GB", "pardiso_iparm15_kb": "kB", "pardiso_iparm16_kb": "kB",
        "pardiso_iparm17_kb": "kB"},
    "results/verification/v4/workflow.csv": {
        "search_s_median": _S, "cert_s_median": _S, "workflow_s_median": _S, "workflow_s_p25": _S,
        "workflow_s_p75": _S, "workflow_s_min": _S, "workflow_s_max": _S, "workflow_s_median_certified": _S,
        "workflow_s_min_certified": _S, "workflow_s_max_certified": _S, "workflow_total_h": "h",
        "workflow_s_per_certified_design": "s per certified design"},
    "results/verification/v2/matrix.csv": {},
    "results/verification/v2/T12_v2.csv": {},
    "results/verification/v2/expectations.csv": {},
    "results/verification/v2/replays.csv": {"seconds": _S},
    "results/verification/v6/T7_v6.csv": {
        "cell_mm": "mm", "E100_guarded_lower_MPa": "MPa", "E100_margin_pct": "%", "G_guarded_lower_MPa": "MPa",
        "gap_safe_kHz": "kHz (interval lo-hi)", "gap_margin_lo_pct": "%", "gap_margin_hi_pct": "%",
        "min_solid_mm": "mm", "min_channel_mm": "mm", "printer_limit_mm": "mm", "time_session_s": _S,
        "time_certify_s": _S, "k_hom_kN_mm": "kN/mm", "deflection_mm": "mm", "deflection_margin_pct": "%",
        "deflection_size_corrected_mm": "mm", "time_macro_s": _S, "T_long_band_mean_dB_n16": "dB",
        "T_shear_band_mean_dB_n16": "dB", "T_long_band_mean_dB_n24": "dB", "T_shear_band_mean_dB_n24": "dB",
        "time_chain_s": _S, "recheck_density_diff_pct": "%", "recheck_E100_diff_pct": "%",
        "recheck_gap_safe_kHz": "kHz (interval lo-hi)", "time_recheck_s": _S, "A3_delta_long_dB_n16": "dB",
        "A3_delta_shear_dB_n16": "dB", "A3_delta_long_dB_n24": "dB", "A3_delta_shear_dB_n24": "dB"},
    "results/claims_ledger.csv": {},
}
_UNIT_LIKE = re.compile(r"(?:^|_)(?:s|seconds|h|mb|gb|kb|mpa|gpa|khz|hz|mm|pct|db)(?:_|$)|per_s$", re.I)


def _unit(path: str, col: str) -> str:
    m = UNITS[path]
    if col in m:
        return m[col]
    assert not _UNIT_LIKE.search(col), f"{path}: column {col!r} looks unit-bearing but has no entry in UNITS"
    return ""


DATA_FILES = [
    # (path, description, writer)
    ("results/atlas/atlas_nu0.3.jsonl", "search atlas at ν_s = 0.3: one search-tier evaluate row per cell (static n 20, "
     "bands n 10), band diagram kept; normalized units (E_s = 1, f* = f a / c_t)", "scripts/atlas/run_atlas.py "
     "(amm.atlas.run)"),
    ("results/atlas/atlas_nu0.342.jsonl", "search atlas at ν_s = 0.342 (same fields)", "scripts/atlas/run_atlas.py"),
    ("results/atlas/atlas_nu0.39.jsonl", "search atlas at ν_s = 0.39 (same fields)", "scripts/atlas/run_atlas.py"),
    ("results/atlas/error_model.json", "calibrated one-sided search-tier error ranges per family and quantity, thin-cell "
     "ranges, calibrated domain", "scripts/atlas/calibrate.py, extend_calibration.py"),
    ("results/atlas/calibration.json", "reference values (converged) and search-tier values of the calibration cells",
     "scripts/atlas/calibrate.py"),
    ("amm/data_manifest.json", "runtime data manifest (amm-data/1): files, sizes, hashes; zenodo and license still null",
     "scripts/software/make_data_manifest.py"),
    ("results/software/contract_amm-tools-3.json", "frozen tool contract: tools, argument schemas, result schemas, "
     "profiles, outcomes, refusal rule", "scripts/software/write_contract.py"),
    ("results/verification/registry_rows.csv", "V1a: amm static homogenization against the registry rows (2609.14741)",
     "scripts/experiments/registry_row_check.py"),
    ("results/verification/v1b/T4_v1b.csv", "V1b: two-sided comparison of amm bounds and gap edges with the Q2-FCM "
     "reference on six cells", "scripts/verify/v1b/compare.py"),
    ("results/verification/dolfinx/summary.csv", "V1c: amm certified gap edges against the DOLFINx-MPC comparison "
     "implementation (8 cases)", "scripts/verify/dolfinx/compare.py"),
    ("results/verification/v14/bench/runs.csv", "V3: one row per (target, method) of the held-out search benchmark, "
     "certificates re-judged by the released rules", "scripts/experiments/v14_rule_rescore.py (rows by scripts/verify/v3/driver.py)"),
    ("results/verification/v14/bench/T5_v3.csv", "V3: per-method summary (table T5 source), certificates re-judged by the released rules", "scripts/experiments/v14_rule_rescore.py; scripts/verify/v3/analyze.py --out results/verification/v14/bench"),
    ("results/verification/v4/throughput.csv", "V4: search-tier throughput by family, batch and threads",
     "scripts/verify/v4/throughput.py, tables.py"),
    ("results/verification/v4/latency.csv", "V4: tool latency per call", "scripts/verify/v4/latency.py, tables.py"),
    ("results/verification/v4/cert_times.csv", "V4: certificate wall time by source and target type",
     "scripts/verify/v4/tables.py"),
    ("results/verification/v4/scaling.csv", "V4: solve time against resolution and unknowns",
     "scripts/verify/v4/scaling.py"),
    ("results/verification/v4/workflow.csv", "V4: spec-to-certified-design time per V3 run",
     "scripts/verify/v4/tables.py"),
    ("results/verification/v2/matrix.csv", "V2: capability and interface acceptance matrix, one row per check and "
     "interface, with expectation, observation, result and cause", "scripts/verify/v2/build_tables.py"),
    ("results/verification/v2/T12_v2.csv", "V2: counts per capability group and interface (table T12 source)",
     "scripts/verify/v2/build_tables.py"),
    ("results/verification/v2/expectations.csv", "V2: expectations written before the run", "scripts/verify/v2/"
     "matrix_spec.py"),
    ("results/verification/v2/replays.csv", "V2: replay result of every session log", "scripts/verify/v2/replay_all.py"),
    ("results/verification/v6/T7_v6.csv", "V6: engineering cases (table T7 source)", "scripts/verify/v6/build_t7.py"),
    ("results/verification/v6/case1/chain_design_n24.json", "V6: 6-cell transmission of the mount design at n = 24 "
     "(same layout for reference and n = 16)", "scripts/verify/v6/chain.py"),
    ("results/verification/v6/case1/macro_design.json", "V6: mount stiffness checks (homogenized block, 3×3×3 voxel "
     "block, size effect)", "scripts/verify/v6/macro.py"),
    ("results/verification/v6/case1/recheck_design.json", "V6: exported-STL recheck of the mount design",
     "scripts/verify/v6/recheck.py"),
    ("results/bench/e4/scores.json", "E4: scored outcome per job (frozen checker)", "scripts/bench/e4.py (score)"),
    ("results/bench/e4/analysis_A2.json", "E4: amended analysis A2 (primary and Holm-adjusted secondary tests)",
     "scripts/bench/e4.py (analyze, amended)"),
    ("results/claims_ledger.csv", "the numbers of the paper assets within the ledger's stated coverage (editorial "
     "numbers excluded; see results/claims_ledger.md), each with source, field, script and status",
     "scripts/paper/make_all.py"),
]


def _keys_json(obj, depth=0, prefix="") -> list[str]:
    out = []
    if isinstance(obj, dict) and depth < 2:
        for k, v in obj.items():
            t = type(v).__name__
            out.append(f"{prefix}{k} ({t})")
            if isinstance(v, dict) and depth < 1 and len(v) <= 12:
                out += _keys_json(v, depth + 1, prefix=f"{prefix}{k}.")
    elif isinstance(obj, list) and obj and isinstance(obj[0], dict):
        out += [f"[] {k}" for k in obj[0]]
    return out


LEDGER_CSV = "results/claims_ledger.csv"
LEDGER_ROWS_TOKEN, LEDGER_SIZE_TOKEN = "@@LEDGER_ROWS@@", "@@LEDGER_BYTES@@"


def ledger_selfcount(L: Ledger) -> int:
    """Register the ledger's own row count (this row included) as its last row; call just before L.write."""
    n = len(L.rows) + 1
    L.add("DATA", f"{LEDGER_CSV}.rows", n, LEDGER_CSV, "rows of the final ledger, this row included (counted "
          "after every other row was registered)", status="derived", script=S)
    assert len(L.rows) == n
    return n


def finalize_supplement(n_rows=None):
    """Fill the ledger's row count and size into SUPPLEMENT_data.md after the ledger file is written."""
    p = PAPER / "SUPPLEMENT_data.md"
    if not p.exists():
        return
    t = p.read_text(encoding="utf-8")
    lp = ROOT / LEDGER_CSV
    if n_rows is None:
        t = t.replace(LEDGER_ROWS_TOKEN, "written by the full run").replace(LEDGER_SIZE_TOKEN, "(full run)")
    else:
        with open(lp, encoding="utf-8", newline="") as f:
            n_file = sum(1 for _ in csv.DictReader(f))
        assert n_file == n_rows, (n_file, n_rows)
        t = t.replace(LEDGER_ROWS_TOKEN, str(n_rows)).replace(LEDGER_SIZE_TOKEN, f"{lp.stat().st_size:,}")
    p.write_text(t, encoding="utf-8")


def supplement(L: Ledger):
    D = ["# Supplementary data dictionary", "",
         "Generated by `scripts/paper/docs2.py` (run `scripts/paper/make_all.py`) from the files themselves: column "
         "names and keys are read, row counts are counted (the claims ledger's count is taken after its final row is "
         "registered). Units come from an explicit field-to-unit table per file (`UNITS` in docs2.py), not from the "
         "column-name suffix; a column shown with '-' has no unit: a count, flag, label or identifier, a normalized "
         "quantity (stiffness / E_s, f* = f a / c_t, lengths / a) or a dimensionless ratio or fraction, as the "
         "description says. Which files are released is decided by the release script (plan B7); this list covers "
         "the files the paper's tables and figures read.", "",
         "Common conventions: designs are {family, kind, params} with params as fractions of the cell edge a; "
         "`spec_hash` = first 16 hex of sha256 of the sorted design JSON; code identity `code_hash` and checker identity "
         "`checker_hash` are 16-hex prefixes of sha256 over the source files (amm/tools.py, amm/certify.py).", ""]
    missing = []
    for path, desc, writer in DATA_FILES:
        p = ROOT / path
        if path == LEDGER_CSV:
            # the ledger is written after every asset (make_all.py); its row count and size are filled in by
            # finalize_supplement once its final rows are known, never read from the previous run's file
            D += [f"## `{path}`", "", f"{desc}. Written by `{writer}`. Size {LEDGER_SIZE_TOKEN} B.", "",
                  f"Rows: {LEDGER_ROWS_TOKEN}. Columns:", "", "| column | unit |", "|---|---|"]
            D += [f"| `{c}` | - |" for c in Ledger.FIELDS] + [""]
            continue
        if not p.exists():
            missing.append(path)
            continue
        D += [f"## `{path}`", "", f"{desc}. Written by `{writer}`. Size {p.stat().st_size:,} B.", ""]
        if p.suffix == ".csv":
            with open(p, encoding="utf-8-sig", newline="") as f:
                rd = csv.reader(f)
                hdr = next(rd)
                n = sum(1 for _ in rd)
            D += [f"Rows: {n}. Columns:", "", "| column | unit |", "|---|---|"]
            D += [f"| `{c}` | {_unit(path, c) or '-'} |" for c in hdr]
            L.add("DATA", f"{path}.rows", n, path, "data rows", status="derived", script=S)
            L.add("DATA", f"{path}.columns", len(hdr), path, "header columns", status="derived", script=S)
        elif p.suffix == ".jsonl":
            n, first = 0, None
            with open(p, encoding="utf-8") as f:
                for ln in f:
                    if ln.strip():
                        n += 1
                        if first is None:
                            first = json.loads(ln)
            D += [f"Rows: {n}. Keys of a row:", ""]
            D += [f"- `{k}`" for k in _keys_json(first)]
            L.add("DATA", f"{path}.rows", n, path, "non-empty lines", status="derived", script=S)
        else:
            obj = read_json(path)
            D += ["Top-level keys (two levels):", ""] + [f"- `{k}`" for k in _keys_json(obj)[:40]]
        D.append("")
    D += ["## Session logs and certificates", "",
          "- `session.jsonl` (every session directory): one header record (code and checker identity, schema, profile), "
          "then one record per tool call with arguments, result or error, state hash and timing. `amm.tools.replay` "
          "re-runs it and compares results and state hashes.",
          "- `certificates/<spec_hash>_<target_key>.json`: the certificate (spec, targets, solver settings, checker "
          "hash, blocks static/bloch/as_built, verdict, robust). The certificate JSON embeds the checker hash; the "
          "session header records the tool-code identity. Retain both for complete session provenance (V6 NOTES "
          "8.4).",
          "- `exports/<name>/`: cell.stl and tiled_3x3x3.stl (binary STL, mm), report.json (amm-export/1: outcome, "
          "certificate reference, screening, disclaimers, file hashes).", ""]
    if missing:
        D += ["## Missing", "", "Listed but not found: " + ", ".join(f"`{m}`" for m in missing) + ".", ""]
    L.add("DATA", "n_files_listed", len(DATA_FILES), S, "DATA_FILES", status="derived", script=S)
    L.add("DATA", "n_files_missing", len(missing), S, "listed files not present", status="derived", script=S)
    p = PAPER / "SUPPLEMENT_data.md"
    p.write_text("\n".join(D), encoding="utf-8")
    return [p]


# ============================================================================================================ GUIDE
def guide(L: Ledger):
    def v(rid):
        return _lv(L, rid)

    def c(rid, fmt=None):
        x = v(rid)
        if fmt:
            x = fmt(x)
        return f"{x} [`{rid}`]"

    f2 = lambda x: f"{float(x):.2f}"
    f3 = lambda x: f"{float(x):.3f}"
    pctf = lambda x: f"{100 * float(x):.1f} %"
    neg = lambda x: str(x).replace("-", "−")
    G = []
    G += ["# Writing guide: software paper on amm (target: Advances in Engineering Software)", "",
          "Generated by `scripts/paper/docs2.py` (run `scripts/paper/make_all.py`). Every result number below (a "
          "value measured, counted or computed from a result file, and every threshold or setting taken from the "
          "code or a protocol) is copied from the claims ledger (`results/claims_ledger.csv`) and followed by its "
          "ledger id in brackets; the generator fails if an id is missing. Editorial numbers are not ledger entries "
          "and carry no id: section, table, figure, finding and plan-item numbers, word budgets, dates, character "
          "limits, version and schema names, and the F/T/S/V/E/B labels. Wording follows the plan (`plan/SOFTWARE_PAPER_PLAN.md`, sections 2 and 10, "
          "'Gate outcome' and 'Mid-point review dispositions') and the mid-point review "
          "(`results/audit/midpoint_2026-11-08/report.md`). Delete the brackets when drafting.", ""]

    G += ["## 1. Venue and article type", "",
          "- **Venue: Advances in Engineering Software (Elsevier), research paper.** Decided at the gate (user "
          "decision, 2026-11-08): V1c was adequate, not strong, and V3 showed no clear advantage, so the npj CM and "
          "Materials & Design conditions were not met (plan section 10).",
          "- AES has no dedicated software article type; it publishes research papers, short communications, "
          "technical notes and software reviews (research/venue_software_2026-11-07.md). Write a research paper whose "
          "contribution is a verified design tool and its workflows, not a new physics method.",
          "- Data policy: Elsevier Option C (data availability statement). The venue notes record no word limit; check "
          "the current Guide for Authors before final layout.",
          "- **Framing for AES:** a verified forward design tool plus engineering workflows. Lead with the problem an "
          "engineer has (a periodic cell that must carry load and block a frequency band, in physical units, with an "
          "honest statement of what was checked), then the tool, then the evidence. Do not lead with the agent or the "
          "GUI; do not lead with the optimizer.",
          "- Repeat venue: the author's AES 2026 paper (LLM control of SIMP continuation) is a different topic; say so "
          "in the cover letter (section 9).", ""]

    outline = [(1, "Introduction: problem, gap in existing tools, contributions", 800, "T1"),
               (2, "Related tools and the author's prior work", 600, "T1, T10"),
               (3, "Software design: tool contract, interfaces, sessions and replay", 900, "F1, T2, F2"),
               (4, "Numerical methods: homogenization, Bloch bands, tiered acceptance, bounds, outcomes", 1300,
                "T3, T11"),
               (5, "Verification of the solvers and certificates", 900, "T4, F3, F4"),
               (6, "Capability and interface acceptance", 450, "T12"),
               (7, "Engineering workflows: mount and filter", 1000, "T7, F7, F8"),
               (8, "Search benchmark and performance", 750, "T5, F5, T6, F6, F11"),
               (9, "Optional LLM interface: the E4 bundle experiment", 450, "T8, F10, T13"),
               (10, "Installation, reproducibility, limitations", 600, "T14, T15"),
               (11, "Conclusions", 250, "-")]
    total_words = sum(w for _, _, w, _ in outline)
    G += [f"## 2. Outline and word budget ({total_words:,} words of main text, the sum of the section budgets)", "",
          "| § | Section | Words | Tables / figures |", "|---|---|---|---|"]
    G += [f"| {i} | {s} | {w:,} | {tf} |" for i, s, w, tf in outline]
    G += [
          "", "Supplement: METHODS.md (full equations and constants), ANALYSIS_failures.md, SUPPLEMENT_data.md, F2s, "
              "T1 evidence (paper/tables/T1_evidence.md), T13b.", ""]

    G += ["## 3. Notes per section", "",
          "### §1 Introduction",
          "- Problem: coupled stiffness and complete elastic-wave band-gap targets for periodic 3D cells, stated in "
          "physical units, with a clear answer when the request cannot be met.",
          f"- Gap (T1, every cell cited in paper/tables/T1_evidence.md): of the {c('T1:n_tools')} inspected tools, "
          "none documents both homogenized stiffness and 3D Bloch gaps with per-result acceptance checks and refusal "
          f"with bounds. The 2026-11-08 follow-up inspection gave {c('T1:n_resolved_cells')} cells a documented code; "
          f"{c('T1:n_unknown_cells')} cells stay 'unknown' (not documented in the inspected version, which is not "
          f"absence); '?' cells left: {c('T1:n_unverified_cells')}; cells without evidence: "
          f"{c('T1:n_cells_without_evidence')}. Write 'not documented in the inspected version', never 'does not "
          "support'.",
          "- Contributions: section 4 below, with exact scope.", "",
          "### §2 Related work and prior work",
          f"- T1 for tools; T10 for the author's {c('T10:n_entries')} prior papers. State what is credited and not "
          "claimed (section 5).", "",
          "### §3 Software design",
          f"- F1: one contract ({c('T2:schema_version')}, {c('T2:n_tools')} tools; profile B {c('T2:n_tools_profile_B')}, "
          f"profile C {c('T2:n_tools_profile_C')}) behind the library, CLI, browser GUI and MCP server. Outcome schema "
          f"{c('T2:outcome_schema')} with {c('T2:n_outcomes')} values: five physical outcomes plus need_info.",
          "- F2: the mount case in the live GUI after certification (regions 1-8 marked; caption in "
          "paper/figures/CAPTIONS.md). F2s in the supplement shows the steps and two refusal states.",
          "- Sessions are logged and replayable; certificates are written only by the checker.", "",
          "### §4 Methods",
          "- Use METHODS.md sections 3-6 for the equations; T3 for every threshold; T11 for the bounds. Say 'acceptance "
          "under stated discretization, sampling and guard assumptions'. List which guard factors are calibrated and "
          f"on what (METHODS.md section 9: the static factor on {c('METHODS:static_guard.calibration_cells')} held-out "
          "cells; the gap factor on one published "
          "case; the gap order cap not calibrated on held-out cells).", "",
          "### §5 Verification (T4, F3, F4)",
          f"- Registry: {c('T4:registry.agree')} of {c('T4:registry.load_bearing')} load-bearing rows agree, max relative "
          f"error {c('T4:registry.max_rel_err_agree')}.",
          f"- G2 ({c('METHODS:static_guard.g2_cells')} cells): false certifications {c('T4:G2.false_certifications')}, false refutations "
          f"{c('T4:G2.false_refutations')}; the gate was redefined after results; disclose the history.",
          f"- Published gap (Lucklum and Vellekoop 2018): extrapolated upper edge {c('T4:lucklum.ext_hi')} vs paper "
          f"{c('T4:lucklum.paper_hi')} ({c('T4:lucklum.dev_hi')}).",
          f"- V1b two-sided (six cells): bounds/edges {c('T4:v1b.bounds_sound')} sound, {c('T4:v1b.bounds_marginal')} "
          f"marginal, {c('T4:v1b.bounds_unsound')} unsound; claims {c('T4:v1b.claims_agrees')} agree, "
          f"{c('T4:v1b.claims_inconclusive')} inconclusive, {c('T4:v1b.claims_disagrees')} disagree. Use the corrected "
          "thin SL c 0.40 numbers (mid-point blocker 2).",
          f"- **V1c, required wording:** the literal pre-registered gate is **{c('T4:v1c.literal_gate')}** (DOLFINx "
          f"identity residual {c('T4:v1c.identity_max_res_dolfinx')} > {c('T4:v1c.identity_residual_tol')} by the letter); the qualified assessment is "
          "**adequate**. Report both. Sentence to use: \"Cross-checked against a comparison implementation built with "
          f"DOLFINx-MPC: {c('T4:v1c.edges_sound')} sound and {c('T4:v1c.edges_marginal')} marginal guarded edge across "
          f"{c('T4:v1c.cases')} cells under the amended reference procedure, with no unsound edge. "
          f"{c('T4:v1c.cells_exact')} cells use exact geometry; {c('T4:v1c.cells_fcm')} curved cells share amm's voxel "
          "occupancy. The comparison does not establish unsampled-k soundness.\" Keep the original-level variant "
          f"({c('T4:v1c.variant_coarse_marginal')} marginal) next to the amended one.", "",
          "### §6 Capability matrix (T12)",
          f"- {c('T12:n_rows')} rows over {c('T12:n_checks')} checks and five interfaces: {c('T12:recount.pass')} pass, "
          f"{c('T12:recount.refused as expected')} refused as expected, {c('T12:recount.fail')} fail.",
          f"- Report the failures as they are: {c('T12:fail.v2_expectation_or_design')} were V2 expectation or design "
          f"errors (amm correct), re-run with expectations written first where needed "
          f"({c('T12:v2err.replaced_by_addendum')} rows replaced by {c('T12:addendum.rows')} addendum rows, all "
          f"{c('T12:addendum.met')} met; {c('T12:v2err.checked_post_hoc')} corrected predicate checked post hoc; "
          f"{c('T12:v2err.no_rerun_needed')} not re-run because only the n_cells expectation was wrong), and "
          f"{c('T12:fail.app')} was an app/ health bug fixed after V2. No failure was an amm bug; three amm bugs were "
          "found by the probe and fixed before the run.",
          f"- Replay {c('T12:replay.v2_logs')}; the PA12 certificate is identical through MCP, GUI, CLI and tutorial 02.",
          "", "### §7 Engineering workflows (T7, F7, F8)",
          f"- Mount: material and cell a {c('T7:mount design.Material, cell a')}; certified on the first certify call; "
          f"guarded E100 "
          f"{c('T7:mount design.Guarded E100 lower (margin)')}; safe gap "
          f"{c('T7:mount design.Guarded safe gap (margins below / above claim)')}; 6×6×6 block "
          f"{c('T7:mount design.Mount stiffness, 6×6×6 homogenized (guarded C*)')}; design − reference band mean "
          f"{c('T7:mount design.Design − reference, long. / shear (n16; n24)')} against the "
          f"{c('T7:A3.threshold_dB', neg)} dB threshold; exported "
          f"STL rechecked ({c('T7:mount design.STL recheck verdicts (static; gap, safe)')}).",
          f"- **Flags, state them in the text:** the mount is **not robust as built** (erosion by "
          f"{c('METHODS:certify.as_built_offset')} a gives E100 {c('T7:mount design.as_built.erode.E100_MPa')} MPa, "
          f"below the requirement {c('T7:mount design.Requirement')}); the PA12 filter **fails manufacturing "
          f"screening** ({c('T7:filter PA12.Screening: min solid / limit')}); the 316L filter is **not robust** "
          "(dilation breaks the gap counts). The reference octet is also not robust (erosion).",
          f"- The chain is a periodic slab at normal incidence, loss factor η = {c('T7:chain.eta')}; in-band levels "
          f"below about {c('T7:chain.interpretation_floor_dB', neg)} dB mean only 'strongly attenuated'. Claim only the "
          f"{c('T7:A3.threshold_dB', neg)} dB comparison. Axial static load only.",
          "- **S4, required wording:** \"Acceptance thresholds were specified before solver runs; targets were "
          "selected using the atlas, and the logged procedural amendments were applied.\" Summarize the "
          f"{c('T7:v6.deviations')} logged V6 deviations next to the results (T7 notes: reference ranking, size-effect "
          "estimator, STL re-voxelization, case-1 rerun under one code identity, shared-lock timing inflation).",
          "- S4 covers scripted workflows plus the demonstrated browser walkthrough of the mount case (the GUI "
          "reproduced the script certificate); no agent ran these workflows. It is supported only for these "
          "acceptance tests.",
          "", "### §8 Search benchmark and performance (T5, F5, T6, F6, F11)",
          f"- **S3, required wording:** \"On {c('T5:n_targets')} held-out, atlas-derived feasible targets, BO certified "
          f"{c('T5:M4.certified')} designs, atlas-only {c('T5:M1.certified')}, Sobol {c('T5:M2.certified')} and DE "
          f"{c('T5:M3.certified')}. BO showed no clear advantage under the registered rule. Its penalized "
          "final-candidate-index cost was lower than Sobol's; the DE comparison was nonsignificant after Holm "
          f"adjustment.\" Supporting numbers: BO vs atlas-only Holm p {c('T5:M1.holm_p')}; cost vs Sobol Holm p "
          f"{c('T5:M2.cost_holm_p')}; cost vs DE Holm p {c('T5:M3.cost_holm_p')}. Do not write 'certifies no more "
          f"designs' ({c('T5:M4.certified')} vs {c('T5:M1.certified')} is not equivalence) and do not write 'saves "
          "evaluations' without the cost definition "
          f"(every searching method spent {c('T5:budget')} evaluations, atlas-only "
          f"{c('FAIL:v3.evals_spent_atlas_only')}; the cost is the index of the retrospectively identified final "
          "candidate, with failures penalized).",
          "- F5 shows search-tier attainment curves plus certified endpoints; intermediate candidates were not "
          "certified, so there is no certified-success-versus-budget curve.",
          f"- Performance: spec-to-certified median {c('T6:workflow|spec to certified design, BO full (amm search)')} s "
          f"(BO) and {c('T6:workflow|spec to certified design, atlas-only')} s (atlas-only) among successes; "
          f"certificate time (V3) {c('T6:certificate|total, V3 all')} s. These are timings, not evidence of batching "
          "gains or speed superiority.", "",
          "### §9 Optional LLM interface (T8, F10, T13)",
          f"- **S5, required wording (scoped to the frozen implementation):** \"For one Codex repeat, the "
          "bounds–atlas-verdict–certificate bundle increased mean per-spec correctness on "
          f"{c('T8:primary.n_specs')} decided specifications from {c('T8:primary.mean_b', f3)} to "
          f"{c('T8:primary.mean_a', f3)}: +{c('T8:primary.diff', f3)}, 95 % CI {c('T8:primary.ci95')}. The gain chiefly "
          "reflected fewer false refusals; unsupported releases were zero in every arm.\"",
          "- E4 ran on the frozen pre-B1 system; B1 changed the refusal acceptance of one E4 session (C-M13). Do not "
          "present E4 as a measurement of final-release agent behaviour, and do not isolate the certificates' causal "
          "contribution. Label the analysis 'amended (A2)', state the outcome-independent stopping record (T13).", "",
          "### §10 Installation and reproducibility (T14, T15)",
          f"- T14: B7 clean installs of the release wheel (code {c('T14:b7.windows.code')}, checker "
          f"{c('T14:b7.windows.checker')}) passed the CPU subset on Windows ({c('T14:b7.windows.tests')}) and in a "
          f"Linux container ({c('T14:b7.linux.tests')}); the earlier B6 runs ({c('T14:win.tests')}) used older code. "
          f"Full suite after V2: {c('T14:tests.total_after_v2')} tests. CI has never run (no remote).",
          "- T15: V10 replay sets (frozen E4, final release, cross-environment); report the targeted M13 replay as a "
          "decision change caused by the B1 refusal rule, not a numeric difference.", ""]

    G += ["## 4. Contributions with exact scope", "",
          "1. **S1 open software.** A Python library, command line, browser GUI and MCP interface over one tool contract "
          "for cubic cells of three families (TPMS, struts, resonators) against density, E100, G, bulk, ν100 and "
          "complete-gap targets in physical units. The full C*, Zener ratio, band structure and as-built flags are "
          "computed outputs; Zener is not a target. STL export with manufacturing screening (not a printability "
          "claim). BSD-3-Clause, confirmed by the author 2026-11-08; prepared locally for archival release; publication and DOIs pending.",
          "2. **S2 tiered numerical acceptance.** Search tier vs acceptance tier; five outcomes plus information needed; "
          "in profile C every refusal must cite evidence held for the current specification (profile B, the ablation, "
          "does not check). Acceptance under stated discretization, sampling and guard assumptions, not a continuum "
          "theorem.",
          "3. **S3 search benchmark.** Held-out, budget-matched search benchmark; no clear BO advantage (wording in "
          "section 3, §8).",
          "4. **S4 engineering workflows.** Scripted mount and filter workflows plus the demonstrated browser "
          "walkthrough of the mount case; no agent runs. Acceptance thresholds were specified before solver runs; "
          "targets were selected using the atlas, and the logged procedural amendments were applied. All acceptance "
          "tests passed, with the flags above.",
          "5. **S5 (supporting).** The E4 bundle effect on one LLM assistant, amended analysis, frozen implementation.",
          ""]

    G += ["## 5. Delta to prior work (T10) with suggested wording", "",
          "- \"The agent-tool-certificate-GUI-replay architecture follows AgenticTO [F05]; we do not claim it. The "
          "principle of verifying before release and refusing with evidence comes from [F01-F03]; clarification of "
          "incomplete specifications from [F04]. New here are the periodic-cell physics (homogenized C* and 3D Bloch "
          "gaps), the tiered acceptance with its five outcomes, and the engineering workflows.\"",
          "- The registry work [F01] supplied the stiffness-conductivity pairing and the catalogue-retrieval idea; the "
          "thermal module is not part of this paper.",
          "- [F06] (AES 2026) and [F07] (AutoSiMP) are earlier LLM/GUI topology-optimization work: cite them, no "
          "overlap in content.", ""]

    G += ["## 6. Limitations (state them; from plan section 2 and the result NOTES)", "",
          "- No global continuum guarantee of gaps; k-sampling and fitted guards; the gap guard factor is calibrated on "
          "one published case and the order cap is not calibrated on held-out cells.",
          "- Linear elasticity, one isotropic solid, cubic families only, small strain; datasheet material values.",
          "- Gaps are for the infinite lattice; finite blocks were checked only for the mount (normal-incidence slab, "
          "axial static load).",
          "- No printability claim: screening only; as-built is a flag, not a tolerance analysis.",
          "- No usability claim: no participants; V8 cut; the GUI was exercised by scripted clicks.",
          "- E4: one repeat, one LLM family, frozen implementation.",
          "- Packaging: GUI not in the wheel; CI not run; macOS/ARM unsupported (MKL); DOIs pending (licences confirmed by "
          "the author 2026-11-08).",
          "- V1c literal gate weak; three of eight V1c cells share amm's voxel occupancy.", ""]

    G += ["## 7. Likely reviewer objections and answers", "",
          "| Objection | Answer (with evidence) |", "|---|---|",
          "| 'Verified' means what? | Acceptance under stated assumptions; T3 lists every check; METHODS.md §9 lists "
          "calibration sources; V1c reported with the literal weak gate and the qualified adequate assessment. |",
          "| Can an engineer use it? | T12 (five interfaces), T14 (clean installs of the release wheel), docs and "
          "tutorials; F2 shows the "
          "live GUI on the mount case. No usability study is claimed. |",
          "| Where is the engineering value? | T7/F7/F8: two cases with acceptance thresholds specified before solver "
          "runs, the logged V6 amendments stated, exported geometry rechecked, flags reported. |",
          "| Why BO if it shows no advantage? | It is reported as a benchmark, not a claim; atlas-first selection is "
          "competitive (T5); the paper's contribution does not rest on the optimizer. |",
          "| What is new beyond existing tools and AgenticTO? | T1 (inspected evidence per cell) and T10 (credited "
          "architecture); new are the cell physics, tiered acceptance and outcomes. |",
          "| Does the agent result apply to this release? | No; it is scoped to the frozen implementation (T13). |",
          "| Self-overlap with the author's papers? | T10 and the overlap note; different physics and object. |",
          "| Thin features and slow convergence? | Undetermined outcomes are reported, not hidden "
          "(ANALYSIS_failures.md); the ladder climbs before abstaining. |", ""]

    G += ["## 8. Before submission (status of the items found while building the assets)", "",
          "**Pending (needs the author):**",
          f"1. T1: {c('T1:n_unknown_cells')} cells stay 'unknown' after the follow-up inspection; keep them as 'not "
          "documented in the inspected version' or inspect further (paper/tables/T1_evidence.md lists the sources "
          "read). Merge scripts/paper/t1_inspection_2026-11-08.csv into research/related_work.csv if one evidence "
          "file is wanted.",
          "2. Release, after the paper is finalized: the git repository, the first CI run, the Zenodo software, data "
          "and results records and their DOIs. Nothing has been published.",
          "3. Docs that still name amm-tools/2 as current (NOTES_B9 section 3).",
          "",
          "**Done (kept for the record):**",
          "- B7 local release: MANIFEST.in, staged tree with the diagram-rule assertion (scripts/paper_private/ "
          "excluded), clean installs and the CPU subset on the release code (T14).",
          "- V10 replay (T15), including the targeted M13 replay.",
          "- Licences confirmed by the author 2026-11-08: BSD-3-Clause (code), CC-BY-4.0 (data and results archive).",
          "- Certificate provenance, stated: the certificate JSON embeds the checker hash; the session header records "
          "the tool-code identity; retain both (V6 NOTES 8.4, corrected).",
          ""]

    G += ["## 9. Cover-letter points, highlights, statements", "",
          "**Cover letter (points):**",
          "- An open design tool for periodic 3D cells with coupled stiffness and band-gap targets, usable without an "
          "LLM; what it checks and what it does not.",
          "- Evidence: verification against a registry, a published gap and two comparison implementations; a "
          "capability matrix over five interfaces; two engineering workflows with acceptance tests; a held-out search "
          "benchmark reported with its null result.",
          "- Overlap note: the author's AES 2026 paper (LLM control of SIMP continuation) and the AgenticTO preprint "
          "(under review at AEI) share the agent/GUI pattern, credited in T10; this paper's object, physics and "
          "evidence are different. No part of the text or results is reused.",
          "- Code and data: prepared locally for archival release; publication and DOIs pending.", "",
          "**Highlights (≤ 85 characters each; check counts after editing):**",
          "- Open tool designs periodic cells for stiffness and complete elastic-wave gaps",
          "- Certificates combine guarded homogenization with Bloch inertia counts",
          "- Five outcomes: certified, refuted, infeasible, not found, undetermined",
          "- Same tool contract behind library, command line, browser GUI and MCP",
          "- Mount and filter workflows meet acceptance thresholds set before solving", "",
          "**Code availability (draft):** amm 0.2.0 (Python), the GUI (app/, web/), tutorials, tests and the scripts "
          "that regenerate every table and data figure are prepared locally for archival release; publication and "
          "DOIs pending; licence BSD-3-Clause (confirmed by the author 2026-11-08). The main overview diagram (F1) is supplied as a rendered file "
          "only.",
          "**Data availability (draft):** the search atlas and error model (data bundle amm-data/1), the verification "
          "results, session logs, certificates and the claims ledger (software tree), and the frozen STL files read "
          "by F7 (results archive) are prepared locally for archival release; publication and DOIs pending; licence "
          "CC-BY-4.0 (confirmed by the author 2026-11-08). See the supplementary data dictionary.",
          "**Declaration of generative AI use (draft; adapt to the Elsevier wording):** LLM assistants (Codex, "
          "Claude) were used to write and test parts of the software and analysis scripts and to draft text; the "
          "author checked and takes responsibility for all content. In the E4 experiment an LLM (Codex) was the "
          "object of study.",
          "**Author contributions:** placeholder (CRediT).", ""]
    p = PAPER / "WRITING_GUIDE.md"
    p.write_text("\n".join(G), encoding="utf-8")
    return [p]


def captions(L: Ledger):
    """paper/figures/CAPTIONS.md: captions of every figure. Numbers come from the claims ledger (figure rows written
    by the figure scripts) or are registered here with their source; definitions are checked to exist in the NOTES
    file they cite."""
    lv = lambda rid: _lv(L, rid)
    gw = read_json("results/verification/v6/case1/gui_walkthrough.json")
    v1b_n, dfx_n, v3_n, v4_n = ("results/verification/v1b/NOTES.md", "results/verification/dolfinx/NOTES.md",
                                "results/verification/v3/NOTES.md", "results/verification/v4/NOTES.md")
    # reference uncertainty u: definitions as written in the protocols (checked here, values registered)
    m1 = re.search(r"u = max\(\|d23\| r, ([0-9e.-]+) \|E3\|\)", read_text(v1b_n))
    m2 = re.search(r"u = max\(\|d23\| r, ([0-9e.-]+) E3\), r = h3\^p", read_text(dfx_n))
    assert m1 and m2, "reference-uncertainty definition not found"
    u_floor_v1b, u_floor_dfx = m1.group(1), m2.group(1)
    L.add("CAPTIONS", "u_floor.V1b", u_floor_v1b, v1b_n, f"text at {_has(v1b_n, 'u = max(|d23| r')}", script=S)
    L.add("CAPTIONS", "u_floor.V1c", u_floor_dfx, dfx_n, f"text at {_has(dfx_n, 'u = max(|d23| r')}", script=S)
    p_clip = re.search(r"p is fitted \(clipped to \[([0-9.]+), ([0-9.]+)\]\)", read_text(v1b_n))
    assert p_clip
    L.add("CAPTIONS", "u.order_clip", f"[{p_clip.group(1)}, {p_clip.group(2)}]", v1b_n, "fitted order clip", script=S)
    _has(v3_n, "best-so-far curves: per method and evaluation count")
    _has(v4_n, "Cold = first call of the process")
    # E4 frozen identity (amendment A1 record)
    a1p = "results/bench/e4/amendments/A1.json"
    a1 = read_json(a1p)[0]
    ident = a1["amended_identity"]
    for k in ("code", "checker", "briefs", "data"):
        assert ident[k] == a1["plan_identity"][k], k
        L.add("CAPTIONS", f"F10.e4_identity.{k}", ident[k], a1p, f"[0].amended_identity.{k} (= plan_identity)",
              script=S)
    arms = {arm: sum(int(lv(f"F10:a.{arm}.{k}")) for k in ("success", "correct_refusal", "abstention",
                                                          "false_refusal", "overclaim", "no_answer"))
            for arm in ("D", "B", "C")}
    assert len(set(arms.values())) == 1, arms
    n_arm = arms["D"]
    v3n = int(lv("F6:c.n_V3"))
    eta = lv("T7:chain.eta")
    edge = json.loads(lv("F4:b.edge_status_counts").replace("'", '"'))
    t = ["# Figure captions", "",
         "Generated by `scripts/paper/docs2.py`. Edit wording in the manuscript, not here. Numbers are from the claims "
         "ledger (`results/claims_ledger.csv`, assets F1-F11 and CAPTIONS).", "",
         "**F1 Tool overview.** Four interfaces (library, command line, browser GUI, optional MCP server for an LLM "
         "agent) call one logged tool contract. Search-tier estimates propose designs; the acceptance tier (bounds and "
         "certificates) decides. Arrows to the outcomes show the evidence each outcome requires (contract "
         "amm-tools/3, `evidence_kinds`): a certificate supports certified, refuted or numerically undetermined; a "
         "bound record supports proven infeasible; an atlas or search record supports not found in families. A "
         "request that cannot be stated in solver units ends in information needed. Rendered file only; its drawing "
         "script is not distributed.", "",
         "**F2 The GUI on the mount case after certification** (live session, amm code f1a6d625064a6d18). "
         "1 specification in physical units with normalized values; 2 cell design with atlas suggestions; 3 export "
         "and manufacturing screening; 4 cell preview; 5 band diagram (search tier) with the claimed gap and the "
         "guarded safe interval; 6 effective stiffness: search tier, certificate and guarded bounds; 7 full 6×6 "
         f"tensor; 8 outcome card citing the certificate. Certificate as in the script run: "
         f"{gw['checks']['certify']['verdict']}, guarded E100 ≥ {gw['checks']['certify']['E100_MPa']:.2f} MPa. "
         "Screenshot unchanged except that the caption band added by the capture script was cropped.", "",
         "**F2s GUI steps (supplement).** a-c the mount case: specification and check_bounds, evaluated atlas "
         "suggestion, released and exported design. d-f an earlier live run (code 5970bf55108f1584, contract "
         "amm-tools/2; results/gui/NOTES.md): certificate in progress with cancel, a refusal without evidence rejected, "
         "and a refusal accepted as proven infeasible citing the bound record.", "",
         "**F3 Stiffness verification.** a amm |C*| / E_s against the registry catalogue (arXiv 2609.14741) for the "
         f"load-bearing rows, both on the same voxel mask: {lv('F3:a.series_agree')} rows agree to a relative "
         f"difference ≤ {lv('F3:a.max_rel_err_agree')}; {lv('F3:a.series_bad')} rows (crosses) have a stored density "
         "that differs from the rebuilt mask. b Two-sided check V1b on six cells (E = E100, G, K = bulk): difference "
         "from the reference value R in percent. Bar: amm's guarded interval [lower, upper]; open marker: amm's "
         "extrapolated estimate; grey band: R ± 2u. R and the reference uncertainty u come from three levels E1, E2, "
         "E3 of the Q2-FCM reference: if the sequence is monotone with shrinking steps, an order p is fitted (clipped "
         f"to {lv('CAPTIONS:u.order_clip')}), R = E3 + d23 r and u = max(|d23| r, {u_floor_v1b} |E3|) with "
         "r = h3^p / (h2^p − h3^p); otherwise R = E3 and u = max(|d12|, |d23|) (V1b NOTES 0.4). Intervals beyond the "
         "axis end in an arrow labelled with the clipped value. c One-sided checks: amm's guarded lower bound divided "
         "by an independent upper bound (Q2 FE at n = 20 and 40; scikit-fem with kinematic uniform boundary "
         f"conditions); a ratio ≤ 1 passes: {lv('F3:c.Q2 FE n = 20.pass')}, {lv('F3:c.Q2 FE n = 40.pass')} and "
         f"{lv('F3:c.scikit-fem KUBC.pass')}. d Cut-voxel bias of G for cube-and-bars c 0.7, w 0.2 (G2 study): "
         f"resolutions whose voxel faces coincide with the cell faces ({lv('F3:d.series_aligned')}) against those "
         f"that cut them ({lv('F3:d.series_cut')}); at n = 64 the grid shifts spread G by {lv('F3:d.phase_spread')}, "
         "which is why the static guard solves several grid phases.", "",
         "**F4 Band-gap verification.** a The published complete gap of Lucklum and Vellekoop (2018, ball 0.79a, "
         "beam 0.05a): deviation of amm's edges from the published edges at n = 20, 30, 40, 60 and the O(h) "
         f"extrapolation from n = 40 and 60 (lower / upper {lv('F4:a.extrapolated_dev')}). b Every certified gap case "
         "of V1b (Q2-FCM reference, above the line) and V1c (DOLFINx-MPC comparison implementation, below): claim "
         "(black), amm's guarded safe interval (blue), reference gap [R_lo, R_hi] (light grey) and each reference "
         "edge ± 2u (dark grey). The reference edge and u follow the three-level rule of F3b, with the floor "
         f"{u_floor_v1b} |E3| in V1b and {u_floor_dfx} E3 in V1c (V1c NOTES, acceptance rule); triangles mark marginal "
         "edges. c Margin of each safe edge inside the reference edge in units of 2u (sound ≥ 1; marginal within "
         f"± 1; unsound below −1); edge statuses over the plotted cases: "
         + ", ".join(f"{k} {v}" for k, v in sorted(edge.items())) + ". V1c registered gate: literal weak (identity "
         "residual), qualified adequate.", "",
         f"**F5 Search benchmark V3** ({lv('T5:n_targets')} held-out targets, budget {lv('T5:budget')} search-tier "
         "evaluations, one seed). a Search-tier attainment curves: for each method and number of search-tier "
         "evaluations, the fraction of targets whose best design so far, chosen by the method's own objective, has "
         "nominal search-tier slack > 0 against every target (V3 NOTES section 5). These are estimates, not "
         f"certificates; the curves of {lv('F5:a.identical_curves').replace(' = ', ' and ')} coincide. Diamonds at the right: fraction of "
         "targets whose final design was certified (only final designs were certified, so there is no "
         "certified-success-versus-budget curve). b Certificate outcome of each method's final design per target: "
         "certified, undetermined, refuted, or a search-tier miss (final design with negative nominal slack, no "
         "certificate requested).", "",
         "**F6 Performance V4** (RTX 4090, i9-13900KF, one machine, one run per point). The panels use different "
         "timing populations. a Search-tier throughput of `evaluate` at 16 MKL threads, one fresh process per family "
         "and batch size: warm median and range over the warm calls of that process (cells/s); crosses: the cold "
         "first call of the process (Python import excluded). b Tool latency through `Session.call` in a fresh "
         "process (profile C), median and range over n calls; tools with a median below 0.01 s are omitted. c "
         f"Wall time of the {v3n} unique V3 certificates (no rerun), one certificate process at a time at 16 MKL "
         "threads, as-built block off, checker f141e46cb67a78db at the V4 run; boxes by target type, points coloured "
         "by verdict. d Solve time against unknowns for cube-and-bars c 0.6, w 0.2, one fresh process per point at 16 "
         "threads: static homogenization (CPU, minimum of 2 repeats), one Bloch inertia count at one shift (CPU) and "
         f"dense Bloch bands at one k (GPU; out of memory at {lv('F6:d.gpu_oom')}).", "",
         "**F7 Case gallery.** For each certified design: exported cell STL, exported 3×3×3 STL, search-tier band "
         "diagram with the claimed gap (dark) and guarded safe interval (light), and the evidence summary. Flags in "
         "colour: not robust as built (mount design, mount reference, 316L filter) and failed screening (PA12 filter).",
         "",
         "**F8 Mount checks.** a Mount stiffness from the guarded C* (uniaxial estimate, homogenized 6×6×6 FE block, "
         "size-corrected) against the 7.2 kN/mm requirement. b Finite 3×3×3 voxel block against the homogenized block "
         "at the same resolution. c In-band mean transmission of the 6-cell slab; labels give design minus reference. "
         f"d, e Transmission spectra (periodic slab, normal incidence, η = {eta}) for longitudinal and shear drive at "
         "two meshes; claimed gap and guarded safe interval shaded.", "",
         "**F10 E4 bundle experiment** (one Codex repeat, confirmatory briefs, amended analysis A2). Frozen "
         "implementation: E4 ran on the pre-B1 system with tool code "
         f"{lv('CAPTIONS:F10.e4_identity.code')}, checker {lv('CAPTIONS:F10.e4_identity.checker')}, brief set "
         f"{lv('CAPTIONS:F10.e4_identity.briefs')} and data {lv('CAPTIONS:F10.e4_identity.data')} (amendment A1 "
         "changed only the harness and the pre-registration); the results do not measure the final release. a "
         f"Outcome of each of the {n_arm} briefs per arm: D LLM alone, B with the spec, search and submit tools, C "
         "with B plus check_bounds and certify. b Differences in per-specification means with 95 % confidence "
         "intervals: the primary test H1 (correct, C − B; paired sign-flip permutation p) and the Holm-adjusted "
         "secondary tests; n is the number of decided specifications in each test.", "",
         "**F11 Search atlas.** Each panel is one solid Poisson ratio. Points: valid atlas cells with a complete gap, "
         "search-tier E100 / E_s against the widest complete gap (width / mid frequency); lines: per family, the "
         "cells not dominated in both quantities. Cells without a gap are not shown (count in each panel). Values are "
         "search-tier estimates, not certificates. Certification markers: circles mark atlas cells certified as "
         f"witnesses of E4 briefs ({lv('F11:certified_witness_cells')} unique cells, truth records in "
         "bench/v1/briefs); diamonds mark atlas cells certified as V3 final designs that are not also witnesses. A "
         "marker records an acceptance-tier certificate of that cell for its brief's or target's requirement; it is "
         "drawn at the cell's search-tier position (at the axis floor when the cell has no gap).", ""]
    L.add("CAPTIONS", "F2.E100_MPa", f"{gw['checks']['certify']['E100_MPa']:.2f}",
          "results/verification/v6/case1/gui_walkthrough.json", "checks.certify.E100_MPa", unit="MPa", script=S)
    L.add("CAPTIONS", "F10.briefs_per_arm", n_arm, "results/bench/e4/scores.json",
          "sum of F10 outcome counts per arm (equal for D, B, C)", status="derived", script=S)
    p = PAPER / "figures" / "CAPTIONS.md"
    p.write_text("\n".join(t), encoding="utf-8")
    return [p]


ALL = [methods, supplement, guide, captions]
