# V21: held-out test of the released gap guard (protocol)

Written 2026-11-10, before any held-out cell was drawn, evaluated, certified or referenced.

- **Why:** confirm round 3. Every reviewer asked for a held-out test of the released gap guard (`_audit_loop_V3/confirm3/reports/verdict.md` §4).
- **Approval:** the author wrote "Held-out test + fixes" on 2026-11-10.
- **Freezing:** the SHA-256 of this file is recorded in `FROZEN.txt` before the first run.
- **Changes:** this file is not edited after that point. Any deviation goes in `NOTES.md` as a dated entry saying when it was decided relative to the results.

## Frozen code

**amm side.** Use the released amm working tree with checker identity `f99ce2b2f65d7630` and code `bb1a90cdc52b7f93`. The driver asserts the checker identity before every certificate. The gap guard, factor, order cap, feature rule and k sampling are used at their defaults.

**Reference side.** Use the existing DOLFINx exact-geometry pipeline unchanged: `scripts/verify/dolfinx/` (`run_case.py`, `bloch_dolfinx.py`, `compare.py`). It runs DOLFINx 0.11.0 and dolfinx_mpc 0.11.0 in the container `amm/dolfinx-mpc:0.11.0-complex`, which has 8 cores. This is the same procedure as V18:
- the mesh is the exact union of boxes on breakpoint-aligned grids, with Q2 elements;
- levels are n = 10, 15, 20 on the certificate's k set plus DOLFINx's own k search;
- n = 30 is solved at the two edge k.

## Cells

There are ten new cube-and-bar cells (family `resonator`, kind `cube_bars`). They are drawn with `numpy.random.default_rng(20261110)` in this order:

- **Stratum T (thin connectors, 3 cells):**
  - c ~ U[0.40, 0.75]
  - w ~ U[0.06, 0.10]
- **Stratum R (regular, 7 cells):**
  - c ~ U[0.40, 0.75]
  - w ~ U[0.10, 0.25]
- **Poisson ratio:** ν_s is drawn uniformly from {0.3, 0.342, 0.39}.
- **Rounding:** c and w are rounded to 4 decimals.

Each draw is tested in order, and the first draws that pass fill the stratum.

**Rejection rules.** A draw is rejected, and the rejection recorded, when any of these holds:
1. The geometry is invalid for the family, i.e. w ≥ c or the evaluator reports `valid: false`.
2. It lies within 0.02 in both c and w of a cube-and-bar cell used earlier in this study. That set covers:
   - the 50-cell set (`results/g2/classification_v3.json`);
   - the phase ladders (`results/g2/phase_ladder`);
   - the V1c and V18 cells (`results/verification/dolfinx/inputs`);
   - the independent-FE cases (`results/verification/indep`);
   - the search-benchmark certificates (`results/verification/v3/certs`);
   - the engineering cells.
3. The search-tier evaluation (`amm.evaluate`, n_bloch = 10, its defaults) shows no complete gap with relative width ≥ 0.10.

## Claims (two per cell, fixed by the search-tier gap)

Let [g_lo, g_hi] be the widest search-tier gap (the evaluator's first entry in `gaps`) with band index nb, and let W = g_hi − g_lo. The two claims are:
- **Claim A (interior):** [g_lo + 0.25 W, g_hi − 0.25 W].
- **Claim B (near-edge):** [g_lo + 0.05 W, g_hi − 0.05 W].

The search tier overstates the upper edge (§4.5 of the paper), so B is expected to include false claims.

**How each claim is certified.**
- Call `amm.certify.certify(spec, {"gap": claim}, nu=ν_s, as_built=False)` with every other argument at its default.
- There is no static target. The surface-offset flag is not part of acceptance, so it is skipped to save time.
- The verdict is the certificate's `verdict`: certified, undetermined or refuted.

## Reference and grading

**Building the reference.** The reference for a cell comes from the case file exported from the claim-B certificate (its 37 k and its band index). It follows the V18 rule:
1. Use levels [15, 20, 30] when the n = 30 edge-k level exists, and [10, 15, 20] otherwise.
2. Take the edges over the finest level's k set.
3. Apply `compare.extrapolate` with h = 1/n, the order clipped to [0.5, 4] and u ≥ 10⁻⁴ E₃. The result is R ± 2u per edge.

If Q2 at n = 30 runs out of the container memory, that cell uses [10, 15, 20]. This rule is fixed now.

**Per edge with a safe value.** Edges are graded for both certificates of a cell:
- **Sound:** the safe edge clears R ± 2u on the conservative side.
- **Marginal:** the safe edge lies within R ± 2u.
- **Unsound:** the safe edge lies beyond R ± 2u on the unsafe side.
- **Unsound for certain:** additionally, on these exact cells, a safe upper edge above the finest DOLFINx upper edge (a Rayleigh–Ritz upper bound at that k).

**Per claim.**
- **True:** [f_lo, f_hi] ⊂ [R_lo + 2u_lo, R_hi − 2u_hi].
- **False:** f_lo < R_lo − 2u_lo or f_hi > R_hi + 2u_hi.
- **Indeterminate:** anything else.

**Primary outcome.**
- (a) The number of unsound safe edges.
- (b) The number of certified false claims.

The guard passes the held-out test if both are zero. A certified indeterminate claim is reported separately.

**Secondary outcomes.**
- Yield: certified true claims as a share of true claims.
- Abstentions and their reasons.
- The fraction of the reference gap that the safe interval gives up.
- Whether the k sampling missed an extremum: the DOLFINx search finding a more extreme k than amm's set.

All results are reported whatever they show. No cell, claim, rule or level is changed after a held-out amm or DOLFINx number exists.

## Budget

- amm side: about 20 certificates on the CPU, plus the GPU for the k search.
- DOLFINx side: about 15–20 min of container time per cell.
- Total about 4–8 h. No LLM calls.
