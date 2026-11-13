# Verification log (week 1, 2026-11-03)

Tests: `python -m pytest -q` → 27 passed (core 13, bounds 8, mutations 6) at week 1; 32 passed on 2026-11-04 after
the G2 additions (three-resolution static guard, grid-phase term, cut-voxel and phase tests); 35 passed after the G2
fixes (phase-mean static guard, interior-k mutation, partial-voxel solver retry). G2 is in `results/g2/NOTES.md`.

## 1. Cross-check against the registry catalogue (arXiv 2609.14741), row by row

`scripts/experiments/registry_row_check.py` reads `external/registry/data/catalogue.csv` (data only; no registry code
is run). It rebuilds each row's binary mask from its stored (family, mode, freq, n, level, tie) with the published
level-set formulas, and solves it with our homogenizer using the same element (trilinear hex8), E = 1 and ν = 0.3.

**Sample of 41 rows** (3 per family × mode, CPU-built, fully connected, n ≤ 48):
- 35 of the 37 load-bearing rows agree to machine precision (relative error of C* about 1e-14). Two independent
  codes give the same answer on the same mask.
- 2 rows (uid 576 IWP, uid 1045 Fischer-Koch S) differ by 4–6e-4. In both, the **stored density does not match the
  mask rebuilt from the stored parameters** (Δρ = 3.6e-4 and 8e-5), and no tie rule (legacy, include, exclude)
  reproduces it. So these rows were solved on a different mask from the one their parameters describe, likely from
  the registry's symmetry or thin-row re-solves. **This is a provenance gap for the registry paper's authors, not a
  solver disagreement.**
- 4 rows (Schwarz P and Neovius network, periodicity 111) are non-percolating cells. Both codes give |C*| ≈ 1e-15,
  our percolation test says they do not percolate, and the registry flags them `feasible = 0`.

**Full run over every eligible row** (`registry_rows.csv`, `registry_rows_summary.json`): 814 rows (CPU-built, fully
connected, n ≤ 48), 805 of them load-bearing.
- **800 of the 805 agree to ≤ 8.6e-14** (median 7.7e-15). That is every row whose stored density equals the density
  of the mask rebuilt from its parameters.
- The 5 that do not agree all carry **`feasible = 0`** in the registry, so its search never returns them:
  - uids 219, 231, 576, 624 and 1045 (Schwarz P, IWP and Fischer-Koch S network);
  - each has a stored density that differs from the rebuilt mask (Δρ up to 4e-3);
  - uid 219 has a stored C11 of 0.0081 against 0.039 for the mask its parameters describe.

  These look like symmetry-broken "legacy" masks that the registry later excluded. For the registry paper it would be
  worth recording which mask each excluded row was solved on.
- The 9 non-load-bearing rows give |C*| ≤ 3e-14 in both codes, and our percolation test agrees with the registry
  flag.

## 2. Physical bounds (`amm/bounds.py`, `tests/test_bounds.py`)

- **Soundness:** 15+ computed designs (4 TPMS × 2 densities × 2 modes, 3 strut lattices, 2 resonators), posed back as
  requests at their own achieved values, are never refuted, and every ratio to the Voigt bound is ≤ 1.
- **Refusals:** each is tested.
  - unit slip (the solid's own modulus requested at 30% density) → V1;
  - ν100 ≥ 1/2 → S1, scoped to the cubic design space;
  - a gap containing f = 0 → W1;
  - contradictory min/max → P1;
  - a frequency in Hz with no cell size → UNDERSPECIFIED. The checker asks; it never guesses.
- **Hashin–Shtrikman audit** (`scripts/experiments/hs_audit.py`, 43 cubic cells at n = 24; corrected 2026-11-08 from 40 to match `hs_audit.json`):
  - no cell exceeds the isotropic HS bounds;
  - the maxima are K/K_HS = 0.948, C44/μ_HS = 0.983, (C11−C12)/2/μ_HS = 0.986 and E100/E_HS = 0.918;
  - HS stays **advisory** for cubic requests. It is rigorous only for isotropic ones, and the observed 0.986 leaves
    no room for a false refusal.

## 3. Mutation tests (`tests/test_mutations.py`)

| Seeded fault | Caught by |
|---|---|
| Ligaments thinner than 1% voxel coverage (a floating core) | Static block: percolation. This test first exposed a **crash**: PARDISO error -4 on the singular K. Certificates now fail closed: percolation is checked before solving, and any solver error is a refusal |
| Gap claim true at n = 10 but false at n = 20 | Bloch block: two-resolution requirement |
| Stiffness claim 20% above what was achieved | Static block target check |
| Density above the requested maximum | Static block target check |
| Gap claim that holds at both n = 20 and n = 30 but not in the converged limit (§4) | Bloch block: edge-convergence guard |
| Cut-voxel bias: G claim true at phase 0 on three resolutions, false over grid phases (real c 0.7 w 0.15 values) | Static block: 5-phase means, order cap 1 |
| Gap that closes only in a small ball around an interior k (injected band bump, radius 0.12 pi) | Bloch block: adversarial k search (path and random sampling miss it) |
| Partial voxel with a rank-6 stiffness making K singular (`tests/test_fcm_retry.py`) | Static row: retry with the finite-cell stiffness floor, recorded per row |

## 4. Published bandgap reproduction

Benchmark: Lucklum & Vellekoop, *Appl. Phys. Lett.* 113, 201902 (2018), doi:10.1063/1.5049663
(`research/gap_benchmark_candidates.md`, `scripts/experiments/reproduce_lucklum2018.py`,
`lucklum2018_*.json`). Simple cubic cell of corner spheres joined by edge beams; E = 3.2 GPa, ρ = 1190 kg/m³,
c_l = 2077.5 m/s, so ν = 0.350 (derived; the paper does not print ν). Frequencies in the paper's f·a/c_l
(= f*/2.0817). Bands from shift-invert Lanczos (PARDISO, real 2N form), finite-cell partial voxels, irreducible-zone
path plus 6 interior points.

**Main cell (ball 0.79a, beam 0.05a; paper: gap 0.0437–0.4702, 166.0 %):**

| n | lower edge | upper edge | gap/midgap |
|---|---|---|---|
| 20 | 0.0488 | 0.4806 | 1.631 |
| 30 | 0.0470 | 0.4785 | 1.642 |
| 40 | 0.0458 | 0.4769 | 1.649 |
| 60 | 0.0451 | 0.4753 | 1.653 |
| O(h) extrapolation from 40, 60 | **0.0437** | **0.4721** | |
| paper | 0.0437 | 0.4702 | 1.660 |

- The gap lies above band 6 at every resolution, as in the paper.
- The X-point modes, extrapolated, are 0.0079, 0.0155, 0.042 and 0.472. The paper gives 0.008, 0.016, 0.042 and
  0.470.
- Both edges converge monotonically from above, at first order in h (thin beams resolved by partial voxels).
  Extrapolated, the lower edge matches the paper to 4 digits and the upper edge is 0.4 % above it. **G1 (within 2 %)
  is met.**

**Variants (gap/midgap ratio):**
- ball 0.78a / beam 0.1a: 1.338 / 1.354 / 1.363 at n = 20 / 30 / 40, against 1.374 in the paper. Still rising,
  0.8 % below at n = 40.
- cube 0.7a / square bar 0.1a: 1.241 / 1.224 / 1.252, against 1.253. Not monotone, because the bar edges align
  with the grid only at some n. 0.1 % at n = 40.

**Soundness finding and fix.** Because both edges converge from above, a claim with upper edge 0.478 passes the
inertia counts at n = 20 *and* n = 30, but it is false in the limit (about 0.470). Agreement of two resolutions does
not protect against a bias they share. The Bloch block now also runs a discretization guard
(`bloch.gap_convergence`, `scripts/experiments/gap_convergence_guard.py`, `gap_convergence_guard.json`):

1. At each resolution, the edges are the largest eigenvalue below f_lo and the smallest above f_hi over **all**
   sampled k (path and interior). Lanczos runs only at the symmetry points, or at the previous resolution's
   extreme. Every other k is screened with one inertia count at the current edge, and any k that goes beyond it
   gets its own solve. So the edges are exact over the sampled set, not just on the path.
2. With the two resolutions (h = 1/n), the edges are extrapolated at first order:
   f₀ = f₂ + (f₂ − f₁)·h₂/(h₁ − h₂).
3. The safe interval is [max(lo₁, lo₂, lo₀ + 2|Δlo|), min(hi₁, hi₂, hi₀ − 2|Δhi|)]. The claim must lie inside it.

| Claim (f·a/c_l) | Counts only (n = 20, 30) | With guard | Safe interval |
|---|---|---|---|
| 0.055–0.478 | passes | **refused** | 0.0488–0.4699 |
| 0.055–0.46 | passes | passes | 0.0488–0.4699 |

The upper safe edge, 0.4699, sits just below the paper's 0.4702 and the n = 60 value, 0.4753.

What the guard is and is not:
- The safety factor of 2 is **calibrated on this one case**. It is not a proof. The inertia counts remain the
  rigorous part of the certificate (exact statements about the discretized model). The guard is an empirical
  protection against discretization bias, and the paper must say so.
- First-order convergence is an assumption. It holds here (monotone, linear in h); grid-aligned cells such as the
  cube variant converge non-monotonically.
- If a third resolution is cheap enough, a convergence-order estimate should replace the assumption. That is open.
- Cost: on this cell (n = 20, 30, 31 k-points), the guard adds about 120 s to the 100 s of counts.

## V19, V20 and the 316L export recheck (2026-11-09, confirm-round fixes)

- Order test corrected (`amm.bloch._order` judged on the order equation in h). Checker f99ce2b2f65d7630, code bb1a90cdc52b7f93. Re-runs of the G2 classification, the v14 rescore, v13 and v12 changed no verdict.
- V19 (`results/verification/v19/rejudge.json`): the 316L filter of V15 becomes certified, safe 28.47-175.27 kHz (upper-edge order 0.93); sound against the V18 exact-geometry reference (margins 3.70 and 19.35 x 2u). PA12 unchanged.
- V16 316L (`results/verification/v16/recheck_316L.json`): exported 316L cell certified at n = 30/40/60, safe 28.58-176.15 kHz, 46 min CPU. Its safe upper edge is 0.09 kHz above the design-cell reference; the exported mesh is a different geometry (edges about 0.8 kHz higher at each resolution), so that reference does not grade it.
- V20 (`results/verification/v20/gci_baseline.json`): three-grid GCI baselines on the V13 near-threshold claims, from stored data.
