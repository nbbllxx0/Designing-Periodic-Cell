# G2 notes (week 2, 2026-11-03 to 2026-11-04)

Gate G2: every seeded fault is caught, and there is no false alarm on 50 clean cells.

**Status after the fixes (section 8): not met on false alarms, met on faults and soundness.**
- Every seeded fault is caught, including a constructed interior-k gap closure.
- Of the 50 cells, 35 are accepted, 4 correctly refused, 5 undetermined (the references cannot settle the claim),
  and **6 are false alarms** (was 8). All 6 are static claims that lie within the guard's safety band; there are
  no gap-guard false alarms (was 3).
- No certified bound lies beyond every estimate of the limit (the first run had one 1 % above it).
- Sections 1-7 describe the first run; section 8 the fixes and the re-run.

Tests: `python -m pytest -q` gives 35 passed (2 min 27 s).

## 1. Cells and claims

- `scan.json` / `scan.log`: GPU n = 12 Bloch scan of 95 cells.
  - 94 cells percolate. 38 have a gap of at least 15 %, and there are 83 gaps in all.
  - The largest excess of an interior-k edge over the path edges is 0.007 (sphere_ligaments c 0.2, w 0.1), at
    n = 12 GPU precision.
- Interior-k mutation: the one candidate re-checked in FP64 was a complex64 artifact (0.9050 vs 0.9065). The other
  candidates were not re-checked, and `path_only_gaps_closed_inside` is empty.
  - So the scan gave no natural cell whose gap closes only inside the zone, and the interior-k gap-closure mutation
    has **no test yet**. It needs a constructed case.
- `selected.json`, `cells/*_m0.05.json`: 50 clean cells (TPMS, struts, resonators).
  - Each cell carries "honest" claims set 5 % inside a first-pass reference. The static reference is O(h) from
    n = 64 and 80; the gap reference is O(h) from n = 30 and 40.
  - `run_m0.05.log` and `analyze.log` record the first pass: 39 of 50 passed.

## 2. First-pass findings

- Static values overshoot the reference widely (`analyze.log`). G overshoots by up to 166 % for cube_bars c 0.8,
  w 0.1.
- The O(h) static reference from (64, 80) is itself unreliable for cube_bars, because the bar faces cut the voxels
  at n = 64 and align with them at n = 80.
- No gap value overshot its reference in the first pass.

## 3. Cut-voxel bias (alignment, element, sub-sample and phase studies)

**Alignment (`alignment_study.log`)**, cube_bars c 0.7, w 0.2, shear modulus G:

| Grid | n | G |
|---|---|---|
| Bar faces aligned with voxel faces | 60 / 80 / 100 | 0.007758 / 0.007687 / 0.007646, smooth and decreasing |
| Bar faces cut | 56 / 72 / 88 | 0.008226 / 0.008127 / 0.007868, 4–6 % stiffer |

The `aligned` flag in that log only tests 0.7n and 0.2n. The faces that matter are the bars at 0.4n and the cube at
0.15n, so read the n values above rather than the flag.

**What does not remove the bias** (`partial_element_study.log`, `element_mix_study.log`, `subsample_study.log`):
- more finite-cell sub-samples;
- trilinear hex8 everywhere instead of incompatible modes (hex8i) in full voxels;
- scaling stiffness by coverage.

The bias depends on where the faces cut the voxels, not smoothly on n. A hex8i element condensed over finite-cell
sub-samples was singular (PARDISO error -4, because voxels with few covered samples get zero stiffness), so it was
abandoned.

**Grid phase.** Translating the periodic cell by a fraction of a voxel changes only the discretization. Any spread
in the results is therefore discretization error.

At n = 64, cube_bars c 0.7, w 0.2 (`phase_study_cube.log`):

| Shift (voxels) | G |
|---|---|
| 0 | 0.008233 |
| 0.2 | 0.008142 |
| 0.25 | 0.008088 |
| 0.4 | 0.007887 |
| 0.5 | 0.007926 |

The spread is about 4 %. `phase_study_families.log` has the same check at n = 48 for other families:
- TPMS: 1e-4 relative or less;
- bcc E100: 0.00840 / 0.00814 / 0.00789, a 6 % spread;
- sc r 0.06: 2 %.

**Consequence.** The guarded three-resolution static block without phases (`static_rerun.json`, 39 of 50 passed)
was **unsound** on cube_bars:
- With n = 32, 48 and 64 all cut, the sequence looks converged.
- For c 0.7, w 0.2 the certified G lower bound was about 0.0081, against 0.00769 at the aligned n = 80.

## 4. Fix: grid-phase term in the static block (`amm/certify.py`)

- At the finest rung, the block also solves the cell at shifts of 0.25 and 0.5 voxel (`STATIC_PHASES`).
- P is the spread of the finest values across phases.
- The certified lower bound is
  `min(values, phase values, ext − 2|d23|, min(phase values) − 2P)`. The upper bound is symmetric.
- A quantity counts as converged only if P/scale ≤ tol.
- A non-monotone step within 2P counts as noise, not divergence.
- The ladder escalates (32-48-64, then 48-64-80) while a claim lies inside the guard band.
- Test: `test_cut_voxel_bias_is_bounded_by_grid_phases`. It uses the computed n = 64 phase values 0.0080876 and
  0.0079265.

**Soundness check.** Stiffness from FE and from finite-cell voxels converges from above. So a certified lower bound
above the smallest computed finest value cannot be right.

Reference values per cell (`static_rerun_phase/`, `lower_over_finest_min`):
- n = 80 at shifts 0, 0.25 and 0.5;
- for TPMS, n = 80 at shift 0 only;
- n = 96 where the first rerun escalated.

Results over the 50 cells:
- 48 cells: lower bound below every reference value.
- **cube_bars c 0.7, w 0.15**: G lower bound 0.003434, 1.03 % **above** the aligned n = 80 value 0.003398. The
  shifts 0.25 and 0.5 at n = 64 put the bar faces at cut fractions 0.2, 0.45 and 0.7. None of these is aligned, so
  P (2 %) misses the full phase range, and the value keeps falling from n = 64 to 80. **This is still unsound.**
- **iwp density 0.15, network**: E100 lower bound 0.013 % above the n = 80 value. This is small, but it is still a
  violation.
- The earlier unsound cases are now below the reference. For example, c 0.7, w 0.2 is now −1.5 %.
- **No accepted claim is false.** The 5 % claim margins absorb the 1 % error, so this soundness hole is in the
  bound, not in any accepted claim.

Possible fixes (not done):
- more phases at the finest rung, with the minimum taken over all of them;
- a phase sweep at two rungs, so that phase and h are separated.

Either fix must be calibrated on cells other than these 50, so that the guard is not tuned on its own test set.

## 5. Gap reference at finer resolution (`gap_ref_fine.py`, `gap_ref_fine/`, `gap_ref_fine.log`)

- Method:
  1. Shift-invert Lanczos at n = 30 at every reference k (G, X, M, R and the scan's extremum k).
  2. The top two k for each edge are kept.
  3. At n = 40 and 50, Lanczos runs only at the kept k.
- The n = 40 edges reproduce the first-pass references, which used an inertia-count screen over every k, for all
  13 cells (agreement to ≤ 5e-8).
- The n = 60 run was stopped for time.
- An earlier fast method took the extremum k from the n = 12 scan. It was wrong for flat resonance bands, and its
  output is kept apart in `gap_ref_fine_discarded/` with a README.
- Gap edges also move non-monotonically with alignment. For example, cube_bars c 0.7, w 0.3 has a lower edge of
  0.4836 / 0.4620 / 0.4690 at n = 30 / 40 / 50.

## 6. Classification (`scripts/g2/classify.py`, `classification.json`)

**How the limit is bracketed.** Candidates:
- the finest value;
- O(h) from the two finest values;
- a fitted-order extrapolation from the three finest values, when the sequence is monotone and contracting.

For static quantities, the bracket's upper end is capped by the smallest n = 80 value over phases.

A claim is **true** if it holds over the whole bracket, **false** if it fails over the whole bracket, and
**undetermined** otherwise.

| Class | Cells |
|---|---|
| Accepted (all true) | 34 |
| Correct refusal (gap claim false) | 4: cube_bars c 0.7 w 0.2, c 0.7 w 0.15, c 0.7 w 0.3; sphere_ligaments c 0.35 w 0.1 |
| Undetermined (references cannot settle the claim) | 4: cube_bars c 0.8 w 0.1 (gap); sphere_ligaments c 0.4 w 0.2 (gap), c 0.35 w 0.15 (G), c 0.3 w 0.2 (G) |
| **False alarm, static** | 5: sphere_ligaments c 0.3 w 0.25, c 0.25 w 0.25; bcc r 0.1 R 0, r 0.1 R 0.15; sc r 0.06 R 0.22 |
| **False alarm, gap guard** | 3: sphere_ligaments c 0.3 w 0.15, c 0.3 w 0.1; bcc r 0.06 R 0.22 (its static block also fails) |

Causes of the false alarms:
- **bcc E100 (2 cells).** The claim is 5 % below the reference, and the n = 80 phase spread of E100 is about 4 %.
  The guarded lower bound misses the claim by 0.3 % and 0.02 %. At this margin, the cut-voxel noise of 45° struts
  at n = 80 is too large to certify.
- **Thin features: sphere_ligaments w 0.25 (2 cells) and sc r 0.06.** E100, G or bulk modulus are not converged by
  the end of the ladder, n = 48-64-80. These need a finer rung (n = 96) or more margin.
- **Gap guard (3 cells).** The counts pass, but the guard assumes O(h). The upper edges converge much faster: the
  fitted order is about 3–4 (p = 3.91 and 3.04). So the O(h) safe interval from n = 20 and 30 is too narrow.

The 4 false gap claims were all refused. The first-pass O(h) reference had placed the lower edge too low.

## 7. Gate tally (first run; see section 8 for the re-run)

| Part of G2 | Status |
|---|---|
| Seeded faults | Caught: floating core, under-resolution, shared discretization bias, overstated stiffness, density, cut-voxel bias (all as tests). Interior-k gap closure: **no test**, because no natural instance exists and none has been constructed yet. Unit slip: covered by the bounds tests (`test_bounds.py`). |
| No false alarm on 50 clean cells | **Not met**: 8 false alarms (5 static, 3 gap guard), plus 4 undetermined |
| Soundness | No accepted claim is false. One static bound is 1 % above the limit (cube_bars c 0.7, w 0.15); see section 4. |

**Open items:**
- grid-phase check in the Bloch block;
- complete phase coverage in the static block (section 4);
- an order-aware gap guard (a third Bloch resolution, n = 40), to remove the 3 guard false alarms without O(h)
  undershoot;
- a constructed interior-k mutation.

## 8. G2 fixes and re-run (2026-11-04)

### 8.1 Classification bug
`scripts/g2/classify.py` had a sign error in the fitted-order extrapolation: it put the fitted candidate on the
wrong side of the finest value. Fixed; the old output is kept as `classification_signbug.json`. One cell changed
class.

### 8.2 Static guard, calibrated on held-out cells
Calibration data: `scripts/g2/phase_ladder.py`, 11 cells **not** among the 50 (flat-faced and thin resonators,
thin struts, two TPMS), at n = 32, 48, 64, 80 x 5 grid phases (0, 1/8, 1/4, 3/8, 1/2 voxel) and n = 96 at phases
0 and 1/2 (`phase_ladder/`, `phase_ladder.log`). Scoring: `eval_static_guards.py`, `score_static_variants.py`.

What the data showed:
- For resonators the converged value can lie 2-6 % below the smallest computed value, because corner and
  cut-voxel error decays slowly (order 0.5-1) and with 2-6 % phase-to-phase noise. "Bound below every computed
  value" is necessary but not sufficient.
- Single-phase sequences jump with the cut pattern; means over phases converge smoothly.

New guard (`certify.static_convergence`, `static_block`):
- every resolution of the rung is solved at 5 phases; the guard works on phase means m(n);
- order p fitted from the three means, capped at `STATIC_P_MAX = 1`; ext = m3 + d23 r, err = |d23| r with
  r = h3^p / (h2^p - h3^p); if the changes are within the noise, err = max(|d23|, P) with P the phase spread;
- lower = min(all values, ext - 2 err), upper = max(all values, ext + 2 err);
- converged if err/scale <= 0.05 and P/scale <= 0.05; ladder (32,48,64) -> (48,64,80) -> (64,80,96).

Held-out result: no bound is past every limit estimate. 1-2 bounds lie about 1 % past the O(h) estimate, which is
inside the reference bracket. The median claim margin the guard needs is 4.7 % on (32,48,64) and 2.4 % on
(48,64,80). With 3 phases instead of 5, 6 and 4 bounds lie past the estimate (worst +3.5 %), so 3 phases were
rejected. A p cap of 2 was also rejected (the cut-voxel test accepts a false claim with it).

### 8.3 Gap guard
`bloch.gap_convergence`, `bloch.certify_gap`:
- edges at three resolutions: n = 20, 30 (with the counts) and n = 40 (Lanczos at the top two k per edge from
  n = 30);
- per-edge fitted order (p in [0.25, 8], capped at `P_MAX = 2`), ext +/- 2 err;
- n = 30 edges at grid phases 0.25 and 0.5 are added as candidates; their spread is the noise level P;
- a non-monotone sequence beyond the noise fails closed; with two resolutions the old O(h) guard is used.

A first version anchored a phase term at n = 30 and over-refused cube_bars c 0.6 w 0.2; it was removed.
`P_MAX = 2` has **no held-out calibration** (`gap_phase_edges.py` covered 4 G2 cells only; shifted grids at n = 20
are unusable for resonators).

### 8.4 Interior-k gap closure
No natural instance exists among the cells. Two measures:
- `certify.bloch_block` now runs `bloch.adversarial_ks` (GPU pattern search over the Brillouin zone at n = 10)
  and adds the k it finds to the count set;
- test `test_interior_k_gap_closure_is_caught_by_the_adversarial_k_search` injects a band bump of radius 0.12 pi
  at an interior k: path plus random sampling passes it, the adversarial search finds it and the certificate
  refuses.

### 8.5 Solver failure on a partial voxel
The re-run hit PARDISO error -4 on iwp 0.15 network, n = 48, phase 0.125. Cause: a partial voxel with one or two
solid sub-samples has a rank-6 midpoint stiffness, and when no other element touches its corner nodes, K is
singular (24 perturbed pivots). Fix: `fem.build_mesh(fcm_alpha=...)`, the finite-cell stiffness floor, used
only as a retry in `certify._static_row` (`FCM_ALPHA = 1e-8`, recorded per row). It changes a healthy solve by
< 1e-8 relative. Tests: `tests/test_fcm_retry.py`. The cell is now accepted. (Bloch meshes do not retry; a
perturbed pivot there fails closed.)

### 8.6 Re-run on the 50 cells (`rerun_v3.py`, `rerun_v3/`, `classify_v3.py`, `classification_v3.json`)
Truth references: the certificate's own solves plus earlier n = 80 / 96 solves (`prior`). At n = 80 those have
3 phases (1 for TPMS), so their means are noisier than 5-phase means.

| Class | First run | Re-run |
|---|---|---|
| Accepted | 34 | **35** |
| Correct refusal (claim false) | 4 | 4: cube_bars c 0.7 w 0.15 / 0.2 / 0.3; sphere_ligaments c 0.35 w 0.1 (all gap) |
| Undetermined | 4 | 5: cube_bars c 0.8 w 0.1, bcc r 0.06 R 0.22, sphere_ligaments c 0.4 w 0.2 (gap); sphere_ligaments c 0.35 w 0.15, c 0.3 w 0.2 (G) |
| False alarm, static | 5 | **6** |
| False alarm, gap guard | 3 | **0** |

Soundness: 16 accepted bounds lie past the bracket's limit side but inside the bracket (worst +0.73 %, 10 of
them density bounds within 0.07 %); every one is at least 4.6 % from its claim. **None** lies past every
candidate. The first run's unsound cell (cube_bars c 0.7 w 0.15) is now refused (gap claim false, static not
converged).

The 6 static false alarms (claim distance from the limit side of the reference bracket):

| Cell | Failing quantity | Claim distance | Guard |
|---|---|---|---|
| sphere_ligaments c 0.2 w 0.2 | G | 2.6 % | err 2.1 %, band 4.2 % |
| sc r 0.1 R 0.15 | G | 3.0 % | err 1.8 % |
| sphere_ligaments c 0.3 w 0.1 | G | 6.9 % | err 5.0 % (not converged) |
| bcc r 0.1 R 0 | E100 | 6.1 % | err 5.8 % (not converged) |
| bcc r 0.1 R 0.15 | E100 | 6.2 % | err 5.4 % (not converged) |
| sc r 0.06 R 0.22 | G | 13.2 % | err 5.7 % (not converged) |

All are claims within twice the remaining discretization error at n = 96. A fourth rung (96, 112, 128),
projected with the fitted orders, would rescue at most the two sc cells; the others need a smaller safety factor,
which the held-out data does not support, or claims with more margin.

### 8.7 Cost
Per cell (`static_seconds`, `bloch_seconds`, MKL 8 threads, two processes in parallel):
- static block: median 198 s, max 2639 s (cube_bars c 0.8 w 0.1, which reaches (64,80,96) at 5 phases);
  18 cells stop at (32,48,64), 11 at (48,64,80), 21 at (64,80,96);
- Bloch block: median 238 s, max 662 s;
- total: median 210 s; 16 of 50 cells exceed the G1 target of 5 minutes.

(The first gyroid record, 1678 s, includes reference solves made by a first version of the script.)

### 8.8 Gate tally after the fixes

| Part of G2 | Status |
|---|---|
| Seeded faults | Caught, all as tests: floating core, under-resolution, shared discretization bias, overstated stiffness, density, cut-voxel bias (phase means), interior-k gap closure (injected), singular partial voxel (retry). Unit slip: `test_bounds.py`. |
| No false alarm on 50 clean cells | **Not met: 6** (static, claims within the guard band), plus 5 undetermined |
| Soundness | No bound beyond every limit estimate; no accepted claim is false |

Open:
- gap `P_MAX = 2` is not calibrated on held-out cells;
- the gap truth reference (n = 50) is only one step finer than the certificate (n = 40);
- certificate time exceeds 5 minutes on a third of the cells.

## 9. Three-way verdict and the G2 definition (2026-11-04)

### 9.1 The change
The certificate was binary: anything not certified counted as a refusal, so G2 called a true claim inside the
guard band a "false alarm". The certificate now returns one of three verdicts, per target and overall
(`certify.static_verdict`, `certify.gap_verdict`, `cert["verdict"]`; `passed` is unchanged and means certified):

| Verdict | Static target (min; max is mirrored) | Gap claim |
|---|---|---|
| certified | converged and guarded lower ≥ target | inertia counts pass everywhere and the edge guard clears the claim |
| refuted | guarded upper < target (needs convergence, except a minimum on E100 / G / bulk, which converge from above) | guarded edges exclude the claim: lower edge ≥ min(computed, ext − 2e) > f_lo, or upper edge ≤ max(computed, ext + 2e) < f_hi |
| undetermined | target inside the guard band, or not converged | everything else |

Failed numerics (disconnected or non-percolating cell) refute the design. A solver error is undetermined.

Count failures alone do not refute a gap claim. Edges converge from above, so a mode inside the interval on a
finite mesh may drop below f_lo in the limit; the band index is not known. When modes lie inside the interval at
every resolution, the verdict stays undetermined with `evidence = "against"`.

Release rule (unchanged): only "certified" releases a design. Undetermined and refuted both block release, so
this change cannot release anything the binary certificate refused.

### 9.2 New G2 definition
The plan's risk 1 already required a three-way verdict for gaps; the static block now follows it. G2 becomes:
1. every seeded fault is caught (never certified);
2. no false certification (certified, claim false) on the 50 clean cells;
3. no false refutation (refuted, claim true);
4. completeness: every true claim that lies outside the guard band at a converged rung is certified;
   abstentions are reported with their reason.

This definition was set **after** seeing the run data. The old binary tally (section 8.6) stays on record next to it.

### 9.3 Result (`scripts/g2/classify_v4.py`, `classification_v4.json`, `classify_v4.log`; no new solves)

| Verdict \ claim truth | true | undetermined | false |
|---|---|---|---|
| certified | 35 | 0 | 0 |
| undetermined | 6 | 5 | 4 |
| refuted | 0 | 0 | 0 |

- False certifications: 0. False refutations: 0. Across the 263 targets: 241 certified, 22 abstentions.
- The 6 old "false alarms" are abstentions:
  - 3 claims inside the band at a converged rung: sphere_ligaments c 0.2 w 0.2 G (claim 2.7 % from the limit,
    band 4.3 %), sc r 0.1 R 0.15 G (3.1 % vs 3.7 %), sphere_ligaments c 0.3 w 0.1 G (7.4 % vs 10.5 %).
  - 3 not converged at (64, 80, 96): bcc r 0.1 R 0, bcc r 0.1 R 0.15, sc r 0.06 R 0.22. The remaining error is
    above the 5 % tolerance.
- Completeness holds: every true claim outside its band is on a non-converged rung, and none on a converged rung
  (`classify_v4.log`, "OUTSIDE BAND" rows are all `converged = False`).
- The 4 false gap claims, refused before, are now undetermined with `evidence = "against"`. 4 of the 5
  undetermined-truth cells carry the same flag. No true claim does, so the flag separates the classes on this
  set (8 of 8 flagged are false or undetermined, 0 of 41 true).
- Tests: `tests/test_verdict.py` (5).

G2 status under the new definition: **met**, with 6 abstentions on true claims out of 41 (15 %).
Remaining cost of abstention: a 4th rung (96, 112, 128) would rescue at most 2 cells (section 8.6) and is
left as an opt-in escalation.
