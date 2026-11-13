# V1b: two-sided verification on six representative cells

Plan item V1b (`plan/SOFTWARE_PAPER_PLAN.md`, section 5 row V1, tables T4, figures F3/F4). Cells:
`cells.json` (written first, before any computation). Scripts: `scripts/verify/v1b/`.

## 0. Protocol (written 2026-11-07, before any independent-vs-amm comparison number was computed)

At the time of writing, only these had run: the amm nominal certificate of the first cell (verdict and safe
interval printed in `amm_nominal.log`), the self-tests of the new solver (homogeneous solid, exact grid-aligned
cell against `indep_fe.Q2Cell`), and timing probes on the Schwarz P cell (Q2 values printed, not compared with amm).
The tolerances and rules below are not changed after comparison numbers exist; any later change is listed under
"Deviations" with its date and reason.

### 0.1 Cells (`cells.json`)

| id | family | source | claims |
|---|---|---|---|
| tpms_schwarzp_d0.25_nu0.3 | TPMS network | G2 clean cell | 5 static + gap (6) |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | TPMS sheet | agent-certified smoke design | G_min, density_max (**marginal**) |
| strut_bcc_R0.27_r0.06_nu0.342 | strut (bcc, node spheres) | E4 certified (A15) | G_min, density_max, gap (12) (**marginal**) |
| strut_octet_r0.06_nu0.3 | strut (octet) | G2 clean cell | 5 static; no complete gap (band comparison) |
| thin_sl_c0.402_w0.061_nu0.3 | thin resonator | E4 certified (G10) | gap (6) |
| thin_sl_c0.357_w0.109_nu0.3 | thin resonator | E4 certified (A09) | gap (6) (**marginal**) |

The first, third and fifth are the V1b cells named in the V1c DOLFINx protocol (same spec, nu and nominal claim).
The 5 cube-and-bars gap cases of V1c are not repeated.

### 0.2 amm side (current code, `run_amm.py`, `amm_side.py`)
- `certify.certify(spec, targets, nu)` with all defaults (static ladder (32,48,64)... at 5 grid phases; Bloch
  counts at n = 20, 30, edges at n = 40 and phases 0.25/0.5; adversarial GPU k search; as-built flag), under the
  shared solver lock, MKL 12 threads. Output `<id>_amm.json`.
- Per-k amm model values (`amm_side.py`, amm's own `fem`/`bloch` code, phase 0): at every compared k, the band
  just below and just above the claim centre (gap cells) or the lowest 15 eigenvalues (no-gap cells), at the
  certificate's resolutions n = 20, 30, 40, and the count below the claim centre.

### 0.3 Independent side
- **Q2-FCM** (`q2fcm.py`; independent of amm, same author): 27-node Q2 hexes on the n^3 voxel grid; geometry
  re-implemented from the family definitions with true periodic images (struts), density-defined TPMS threshold
  from a 256^3 quantile; cut voxels integrated by moment fitting (125 Legendre moments of an anti-aliased indicator
  sampled at 5^3 sub-cubes x 3^3 Gauss points; element matrices exact given the moments); void floor 1e-6;
  homogenization with periodic fluctuations; Bloch at arbitrary k by entrywise Floquet phases exp(i k.d_IJ) on the
  k = 0 matrices; PARDISO through its own ctypes driver (real 2N form, mtype -2: inertia gives the band index;
  shift-invert Lanczos for the eigenvalues). Shared with amm: the design formulas, numpy/scipy/MKL. Not shared:
  element, geometry sampling, quadrature, assembly, Floquet constraint, solver driver.
- **scikit-fem** (`skfem_cells.py`; semi-independent): scikit-fem 12.0.2 `ElementHex2` assembly on the cut-cell
  tensor mesh, its own quadrature (full voxels: 3^3 Gauss; cut voxels: 3^3 sub-cubes x 3^3 Gauss with the SHARP
  indicator, a different geometry integration from Q2-FCM), periodic homogenization through a node-identification
  matrix written here, and KUBC (u = E x on the cell faces). Geometry evaluator shared with Q2-FCM.
- Resolutions. Static Q2-FCM: n = 16, 24, 32. scikit-fem: n = 12, 16 (periodic and KUBC). Bloch Q2-FCM: three
  levels n1 < n2 < n3 = (12, 16, 20) for TPMS and struts, (16, 20, 24) for the thin resonators.
- k-sets. S_amm = amm's path kpath(4) (21 points), its interior ibz_interior(10, seed 0) and the 6 adversarial k
  of the certificate. S_ind = an own adversarial search on Q2-FCM at n = 8 (path with 8 points per leg + 60 random
  interior points, seed 20261108, then a 26-direction pattern search, 5 rounds, step 0.15 pi halving, 2 starts
  per edge) plus 4 random points of the FULL zone outside the irreducible wedge (seed 20261109; tests the cubic
  symmetry assumption). Level n1 evaluates S_amm and S_ind; n2 and n3 evaluate, per edge, the 3 most extreme k of
  n1 plus Gamma, X, M, R. No-gap cells: lowest 15 bands at Gamma, X, M, R and 4 interior points at n1, n2, n3; all
  31 path + interior points at n1.

### 0.4 Reference value and uncertainty (both static and band edges)
From three levels E1, E2, E3 (h = 1/n), same rule as V1c: if the sequence is monotone with shrinking steps,
p is fitted (clipped to [0.5, 4]), R = E3 + d23 r, u = max(|d23| r, 2e-4 |E3|), r = h3^p / (h2^p - h3^p);
otherwise R = E3, u = max(|d12|, |d23|). For band edges the levels use the same k set (the finest level's).

### 0.5 Two-sided discrepancies and acceptance rule
Signed discrepancy (reported for every quantity, two-sided): delta = (amm estimate - R) / |R|, with the amm
estimate = the certificate's extrapolated value (static) or extrapolated edge (gap). Positive = amm above the
reference.

Per guarded bound (static lower L / upper U of E100, G, bulk, density, nu100; gap safe edges s_lo, s_hi):
- lower-type bound B (static lower L; gap upper edge s_hi is mirrored): **sound** if B <= R - 2u (static lower),
  **marginal** if within R +- 2u, **unsound** if B > R + 2u.
  For the gap: s_lo (bound on the top of the band below the gap) is sound if s_lo >= R_lo + 2u_lo, marginal within
  +-2u_lo, unsound if s_lo < R_lo - 2u_lo; s_hi is sound if s_hi <= R_hi - 2u_hi, marginal within +-2u_hi,
  unsound if s_hi > R_hi + 2u_hi.
- conservatism (reported): (R - L)/|R|, (U - R)/|R|, (s_lo - R_lo)/R_lo, (R_hi - s_hi)/R_hi.
- consistency of the estimates: |amm_ext - R| <= 2 sqrt(u^2 + e_amm^2) (e_amm: amm's own remaining-error estimate).
  Reported; an inconsistency is a discrepancy, not a soundness failure.

Per certified claim (nominal and marginal): the independent reference **agrees** if the target clears R by 2u
(min target t: R - 2u >= t; max: R + 2u <= t; gap: [f_lo, f_hi] inside [R_lo + 2u_lo, R_hi - 2u_hi]),
**disagrees** if it misses by 2u (t > R + 2u; gap: f_lo < R_lo - 2u_lo or f_hi > R_hi + 2u_hi), else
**inconclusive**.

k coverage: at n1, Delta_lo = max over S_amm+S_ind of band nb - max over S_amm, Delta_hi = min over S_amm of band
nb+1 - min over S_amm+S_ind. A positive Delta larger than 1e-4 relative is reported with its k; it is a soundness
problem only if it exceeds amm's margin at that edge (s_lo - lo or hi - s_hi at the same level). Band index: the
Q2 inertia count at the claim centre must equal amm's below_band at every k (a mismatch is a gap-closure
disagreement and is listed).

scikit-fem: two-code agreement if |Q_sk(16) - R| <= 2u + 2 |Q_sk(16) - Q_sk(12)| (periodic); KUBC: the old
one-sided check L <= Q_KUBC(16) (approximate: FCM quadrature makes KUBC an upper bound only up to geometry
quadrature error) and Q_KUBC >= Q_periodic at the same n.

No-gap band comparison: per band (4..15, i.e. above the acoustic triplet at Gamma) and k, delta_b = (amm_ext -
R)/R with amm_ext from n = 20, 30, 40 by the same rule; consistent if |amm_ext - R| <= 2 sqrt(u^2 + e^2).

**Verdict rule.** V1b passes (two-sided verified) if: (i) no guarded bound or safe edge is unsound; (ii) no
certified claim (nominal or marginal) disagrees; (iii) no k found by the independent search lies beyond amm's
safe edge by more than 2u at that edge; (iv) no band-index mismatch at a certified claim. Descriptive bands, not
pass/fail: |delta| <= 1 % (TPMS and strut stiffness), <= 3 % (resonator stiffness), <= 1 % (gap edges).

### 0.6 Marginal claims (rule fixed now; claims computed from the pass-1 certificates)
For tpms_schwarzp_sheet_d0.2895_nu0.342, strut_bcc_R0.27_r0.06_nu0.342 and thin_sl_c0.357_w0.109_nu0.3:
- static min target on Q: t = L - 0.01 (ext - L) (1 % of the guard band inside the guarded lower bound L);
- density_max: t = U + 0.01 (U - ext);
- gap: f_lo = s_lo + 0.01 (s_hi - s_lo), f_hi = s_hi - 0.01 (s_hi - s_lo).
They are re-certified with the same amm code (`run_amm.py marginal`, `marginal_claims.json`); only claims amm
certifies count as marginal certified claims. The independent check is the claim rule of 0.5.

## Deviations
1. 2026-11-07 14:08, before any Bloch comparison number existed (only the static comparison of the two TPMS cells
   had been printed): the own adversarial search runs on Q2-FCM at n = 6 (TPMS, struts) / 8 (resonators) instead
   of 8, with 4 pattern rounds instead of 5 and Lanczos tolerance 1e-7 in the search only. Reason: about 2 s per
   evaluation at n = 8 (sparse factorization per k) made the 620-evaluation search cost about 20 min per cell. The
   candidate k it returns are re-evaluated at every level with the full tolerance, so only the search's reach is
   reduced, not the accuracy of the compared values.
2. 2026-11-07 14:45, before any per-k comparison existed: the amm per-k values (`amm_side.py`) use amm's assembled
   matrices and amm's PARDISO real 2N factorization (inertia = count) with the scipy eigsh driver (8 eigenvalues,
   tol 1e-9) instead of amm's InertiaCounter.edge (nev 3), which took about 12 s per k at n = 20; and they are
   computed at n = 20 for every level-1 k but at n = 30 and 40 only for the refinement subset (section 0.2 said
   n = 20, 30, 40 everywhere). The sampled-level per-k comparison is therefore amm n = 20 against Q2 n1.
3. 2026-11-07 15:05, before any scikit-fem value was compared: scikit-fem cut voxels use 2^3 sub-cubes x 3^3
   Gauss points (216 points) instead of 3^3 x 3^3 (729), and the indicator is evaluated once per quadrature point
   (passed to the form) instead of inside the form. Reason: 630 s for one cell at n = 12 (the form is evaluated once
   per basis-function pair, 6561 times). The one n = 12 value computed with the old rule (Schwarz P network:
   periodic E100 0.071356, G 0.010264, bulk 0.026796; KUBC 0.074566, 0.016619, 0.029485) was printed before the
   change and is discarded.
4. Static Q2-FCM levels. n = 40 was added for the two strut and two resonator cells (14:30, after seeing the Q2
   sequences 16/24/32 decrease without a shrinking step, before any comparison was printed); the reference uses
   the three finest levels (24, 32, 40). n = 48 was added for the two thin resonators at 15:15 AFTER the first
   comparison showed amm's E100/bulk lower bounds on thin_sl_c0.402 within 2u of the (24, 32, 40) reference
   ("marginal") and the reference sequence was not clearly asymptotic. Both references are reported
   (`static_ref_alt` in the comparison files); the verdict uses the three finest levels.
5. 2026-11-07 16:00, AFTER the first octet band comparison: (a) the Q2-FCM n = 20 row at R lost copies of the 8-fold
   and 7-fold flat strut bands (Lanczos with nev = 15 returned multiplicities 7, 6, 2; n = 12, 16 and amm n = 20, 30,
   40 give 8, 7), which shifted band indices 8-15 by one. That row was recomputed with nev = 24 (keep 15), checked
   with the PARDISO inertia between the clusters (8 below f* = 0.278, as expected), and written back with the
   original row kept under `replaced_row` (`recheck_degenerate.py`). (b) Per-index extrapolation is meaningless where
   the band index changes cluster between levels (mode crossings / reordering of degenerate clusters, e.g. amm at X:
   4-fold below 2-fold at n = 20, above it at n = 30, 40). Such rows are now flagged (`crossing_q2`, `crossing_amm`)
   and the band statistics are reported both over all rows (the section 0.5 rule) and over the rows without a
   crossing; a finest-level direct comparison (amm n = 40 against Q2 n3) is added. These are descriptive; the band
   comparison carries no claim and no pass/fail weight.
6. 2026-11-07 16:20, AFTER the first gap comparison of thin_sl_c0.402_w0.061_nu0.3 showed the lower safe edge
   "marginal" (s_lo = 0.12058 against R_lo + 2u_lo = 0.12064 from the non-monotone levels 16, 20, 24): Q2-FCM Bloch
   levels n = 28 and 32 were added on the same refinement k subset (`extend_gap_levels.py`,
   `q2/<id>_bloch_extra.json`; identical k evaluated once). The ligament (w = 0.061) spans 1.0-2.0 voxels over these
   levels, so the edge oscillates with grid alignment. As for the static deviation 4, the reference then uses the
   three finest levels and the earlier reference and statuses are kept in the comparison file (`ref_prev`) and in
   the gap table. Only this cell was extended (the only marginal gap status), which is a selective post-hoc
   refinement and is reported as such. The per-k extrapolated comparison of this cell still uses levels 16, 20, 24.
   Outcome (five levels 16-32: lower edge 0.11457, 0.11016, 0.11181, 0.11019, 0.10916; upper edge 0.97494, 0.97230,
   0.97316, 0.97228, 0.97160): with (24, 28, 32) the lower safe edge is sound and the upper safe edge becomes
   marginal (s_hi = 0.95117 against R_hi - 2u_hi = 0.95076; the fit extrapolates with p = 0.70). With (20, 24, 28)
   both are sound; with (16, 20, 24) the lower is marginal. No choice of three levels makes either edge unsound.
7. 2026-11-07 16:20: the TPMS sheet band run was started twice by mistake (once by hand, once by the queued lane D
   script, whose bash process survived the task stop); the second copy (PID 91544) and its lane script were killed
   after about 3 min. Both copies wrote the same deterministic computation; the log file
   `q2_bloch_tpms_schwarzp_sheet_d0.2895_nu0.342.log` was truncated by the second start and is incomplete.
8. 2026-11-07 16:50, AFTER the band comparison of the TPMS sheet showed finest-level differences of -27 % to +20 %
   that come from degenerate clusters reported with different multiplicities (e.g. at R a 5-fold cluster as 4, 5 or
   6 copies by the Lanczos driver of either code): an eigensolver-free check was added (`inertia_bands.py`). At
   every refinement k, probe frequencies are placed in the gaps (> 2 %) between the clusters of the finest Q2
   spectrum, and the number of eigenvalues below each probe is counted by PARDISO inertia for Q2-FCM (n1-n3) and for
   amm's model (n = 20, 30, 40). This tests (a) whether each code's Lanczos spectrum has the right multiplicities
   and (b) whether the two codes agree on the band count below each probe. The Lanczos driver on the amm side is
   the V1b driver of deviation 2 (scipy eigsh), not amm's certificate path, which counts by inertia. Octet: all 8
   refinement k (47 probes). TPMS sheet: only the two k with flagged rows (X and R, 7 probes); the run over all 8 k
   was stopped after its first level because it would have taken about an hour.

## 1. Results (computed 2026-11-07 13:15-17:20)

### 1.1 What was run
- amm (current code, checker hash in each `<id>_amm.json`): 6 nominal certificates, all `certified`, and 3
  marginal-claim certificates (`<id>_amm_marginal.json`, `marginal_claims.json`), all `certified`. Gap safe
  intervals: P-net [0.47988, 0.82789], bcc [0.36772, 0.60146], SL c.40 [0.12058, 0.95117], SL c.36 [0.20247, 0.82270].
- Q2-FCM static at n = 16, 24, 32 (+40 for struts and resonators, +48 for the thin resonators); scikit-fem periodic
  and KUBC at n = 12, 16 for all 6 cells; Q2-FCM Bloch at three levels for the 4 gap cells (+28, 32 for SL c.40) and
  the 2 no-gap cells; amm-model per-k values at n = 20 (all k), 30, 40 (refinement subset); inertia band counts for
  the no-gap cells.
- Files: `compare_<id>.json` (every number below), `summary.json`, `T4_v1b.csv` (table T4 rows, one per check),
  `tables.md` (the tables below), `fig_v1b_stiffness.png` (F3), `fig_v1b_bandedges.png` (F4), raw solver outputs in
  `q2/`, `skfem/`, `<id>_amm_k.json`, `<id>_inertia_bands.json`.

### 1.2 Verdict
**PASS (two-sided verified, with the qualifications in 1.4).** Against the section 0.5 rule:
(i) 0 of 68 guarded bounds / safe edges are unsound (57 sound, 11 marginal); (ii) 0 of 24 certified claims disagree
(23 agree, 1 inconclusive: the marginal density_max of the TPMS sheet, whose margin is below the reference
uncertainty); (iii) no independent k (own search, full zone) lies beyond amm's sample: the k-coverage excess is below
1e-14 on all 4 gap cells and the extreme edges sit at high-symmetry points on amm's path; (iv) 0 band-index
mismatches (the Q2 inertia count at the claim centre equals amm's below_band at every k and level).

The 11 marginal statuses: 8 are density bounds, whose guard band (about 1e-4 relative) is narrower than the Q2
reference uncertainty (soft indicator, about 2-3e-4 relative). The sharp design density (256^3 midpoint sampling) is
inside amm's [lower, upper] for 5 cells; for SL c.40 the sampled value 0.273991 lies 3.6e-5 above amm's upper
0.273955, but the exact analytic volume of the sphere-plus-cylinders cell is 0.2739022, inside amm's bounds (SL c.36:
exact 0.1979265, also inside). One is the octet nu100 (absolute difference -1.3e-4 against 2u = 8.5e-4). One is the
SL c.40 upper gap edge (deviation 6). The bcc density estimate is also flagged inconsistent (amm 0.195107 against
Q2 0.195008 +- 3.9e-5), again the Q2 soft-indicator volume bias; the sharp density 0.195071 is inside amm's bounds.

### 1.3 Two-sided discrepancies (signed; positive = amm above the reference)
- Static, TPMS: |delta| <= 0.62 % on E100, G, bulk (amm below the reference by 0.10 to 0.62 %), inside the 1 %
  band. scikit-fem n = 16 agrees within its rule except P-net E100 and bulk (+0.21 / +0.23 % from the reference,
  flagged DIFF only because scikit-fem's own 12-to-16 step is tiny; not a soundness issue).
- Static, struts: bcc E100 -5.0 %, G -1.2 %, bulk -1.1 %; octet -1.3 to -1.9 %. All amm estimates are below the
  reference and all are consistent within 2 sqrt(u^2 + e^2). bcc E100 is outside the 1 % band (thin struts,
  r = 0.06; the reference itself has 2u = 4.8 %). With the earlier reference (16, 24, 32) the bcc lower bounds and the
  octet E100 lower bound were marginal; with the finest three levels (24, 32, 40) they are sound.
- Static, thin resonators: SL c.40 E100 +1.9 %, bulk +1.9 %, G -29.6 %; SL c.36 E100 +0.3 %, bulk +0.3 %, G -3.4 %.
  The SL c.40 G is a very small modulus (3.3e-4 E_s) that amm itself marks as unconverged (guarded lower bound
  negative, upper +78 %); no claim uses it. All consistent; the 3 % band holds except for both G values.
- Gap edges (amm's extrapolated edges against the Q2 reference): P-net +0.05 / -0.03 %; bcc -0.88 / -4.85 %;
  SL c.40 +4.43 / +0.16 % [corrected 2026-11-08; the earlier +0.44 / -0.63 % did not match the final reference]; SL c.36 -0.38 / +0.01 %. All consistent. The bcc upper edge is outside the 1 % band (the
  reference has 2u = 4 %), in the conservative direction for a gap claim.
- Conservatism of the safe interval (distance inside the reference edge): lower edge 3.4 / 7.6 / 13.8 / 5.5 %, upper
  edge 0.5 / 20.8 / 1.4 / 6.6 % (P-net, bcc, SL c.40, SL c.36).
- Per k, sampled level (amm n = 20 against Q2 n1 at the same 45 k: path, interior, adversarial, own search, full
  zone): amm is above Q2 at every k, by 0.0 to 6 % (expected for hex8 against Q2 at similar resolution). Per k
  after extrapolation: P-net <= 0.15 %, SL c.36 <= 0.39 %, bcc <= 5.2 %, SL c.40 up to -31 % at Gamma and -14 % at R.
  The large values come from applying the three-level rule to amm's n = 20, 30, 40 values with the fitted order
  clipped at 0.5 (a strong downward extrapolation), not from amm's certificate estimator, and all are consistent
  within the combined uncertainty. The certificate's own extrapolated SL c.40 lower edge is +4.43 % from the
  final reference [corrected 2026-11-08 from +0.44 %; `T4_v1b.csv`].
- No-gap bands (octet, TPMS sheet): per-index extrapolated differences reach 17-27 % on rows where a degenerate
  cluster is reported with different multiplicities, or the band order changes, between levels (25 and 18 rows).
  The eigensolver-free counts (deviation 8) show that this is the Lanczos driver losing copies of 4- to 8-fold
  clusters in both codes (never spurious extra copies), not a band-structure disagreement: at all 7 TPMS-sheet probes
  amm n = 40 and Q2 n3 count the same number of bands. On rows without a crossing the TPMS sheet agrees within
  1.7 % (99/99 consistent). The octet rows without a crossing differ by up to 12 % after extrapolation (92/92
  consistent): amm's sequence converges slowly (p 0.7-0.9) and its extrapolation overshoots downwards. At the
  finest levels amm n = 40 is +0.6 to +2.5 % above Q2 n = 20, and all 21 octet probe-count differences have fewer
  amm bands below the probe, i.e. the same frequency offset. The Q2 value lies inside amm's own +-2u at every row
  (at most 0.43 of it).

### 1.4 Qualifications and limitations
- The reference uncertainty is large where features are thin: 2u is 4-5 % of the bcc static moduli and gap edges,
  about 6 % of the SL c.40 lower edge [corrected 2026-11-08 from "about 3 %": final reference u_lo 0.00317 on 0.106], and the Q2 level sequences of the thin resonators are non-monotone
  (ligaments of 1-2 voxels). Soundness is shown at the resolution of that uncertainty, not better.
- Reference levels were extended after seeing comparisons in two places (static n = 48 for the thin resonators,
  Bloch n = 28, 32 for SL c.40; deviations 4 and 6). Both earlier references are reported; none gives an unsound
  status. The SL c.40 safe edges are marginal at one edge or the other under two of the three level choices.
- The own adversarial search ran on a coarse model (n = 6 / 8, deviation 1). It found the extremes at high-symmetry
  points for all 4 gap cells, but at n = 6 the bcc band 13 is poorly resolved (search minimum about 0.85 against
  about 0.6 at n >= 12), so for bcc's upper band the search adds little beyond amm's own k set.
- Q2-FCM and amm share the design formulas, numpy/scipy and MKL PARDISO; scikit-fem also shares the Q2 geometry
  evaluator. scikit-fem was run only at n = 12, 16 (its strut values are 6-9 % above the reference).
- amm per-k values use amm's assembly with the V1b eigen driver (deviation 2), not amm's certificate edge driver.
- CPU threads: several jobs ran concurrently at 4-12 MKL threads each, alongside the V1c DOLFINx jobs, so the
  12-thread limit was exceeded at times (up to about 24-28 threads). This affects timings only.
- Compute: amm certificates 1.46 h (9 runs, under the solver lock); Q2-FCM static 0.31 h, Bloch 2.34 h plus 0.92 h
  extra levels; scikit-fem 0.99 h; amm per-k 1.74 h; inertia counts 0.61 h. In total 8.4 solver-hours over about
  4.1 h of wall-clock time (13:15-17:20), above the 2-4 h target because of the post-hoc checks.
- No amm bug was found.

### 1.5 Tables (generated by `summarize.py` from `summary.json`; nu100 deltas are absolute differences)

#### Static (Q2-FCM reference from the three finest levels; delta = (amm estimate - R)/R)

| cell | Q | R +- 2u | amm est. | delta | amm [lower, upper] | lower | upper | consistent | scikit-fem n16 (per.) | KUBC >= lower |
|---|---|---|---|---|---|---|---|---|---|---|
| tpms_schwarzp_d0.25_nu0.3 | E100 | 0.070962 +- 7.4e-05 | 0.07082 | -0.20 % | [0.069995, 0.071741] | sound | sound | True | +0.21 % DIFF | True |
| tpms_schwarzp_d0.25_nu0.3 | G | 0.010152 +- 3.2e-05 | 0.0101 | -0.51 % | [0.0098313, 0.010416] | sound | sound | True | +0.45 % ok | True |
| tpms_schwarzp_d0.25_nu0.3 | bulk | 0.026629 +- 3.1e-05 | 0.026567 | -0.23 % | [0.026211, 0.026964] | sound | sound | True | +0.23 % DIFF | True |
| tpms_schwarzp_d0.25_nu0.3 | density | 0.24993 +- 0.0001 | 0.25 | +0.03 % | [0.24995, 0.25001] | marginal | marginal | True | n/a | n/a |
| tpms_schwarzp_d0.25_nu0.3 | nu100 | 0.055863 +- 5.6e-05 | 0.055714 | -0.01 % | [0.054945, 0.05657] | sound | sound | True | +0.01 % ok | n/a |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | E100 | 0.082722 +- 5.2e-05 | 0.082209 | -0.62 % | [0.080499, 0.083943] | sound | sound | True | -0.30 % ok | True |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | G | 0.061002 +- 2.4e-05 | 0.06091 | -0.15 % | [0.060582, 0.061285] | sound | sound | True | -0.30 % ok | True |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | bulk | 0.10638 +- 4.3e-05 | 0.10627 | -0.10 % | [0.10598, 0.10663] | sound | sound | True | -0.29 % ok | True |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | density | 0.28944 +- 0.00012 | 0.2895 | +0.02 % | [0.28941, 0.28953] | marginal | marginal | True | n/a | n/a |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | nu100 | 0.37039 +- 0.00015 | 0.37153 | +0.11 % | [0.36829, 0.37477] | sound | sound | True | +0.00 % ok | n/a |
| strut_bcc_R0.27_r0.06_nu0.342 | E100 | 0.0049819 +- 0.00024 | 0.0047324 | -5.01 % | [0.003647, 0.0058398] | sound | sound | True | +8.82 % ok | True |
| strut_bcc_R0.27_r0.06_nu0.342 | G | 0.01605 +- 0.00029 | 0.015865 | -1.16 % | [0.014942, 0.016787] | sound | sound | True | +1.34 % ok | True |
| strut_bcc_R0.27_r0.06_nu0.342 | bulk | 0.01705 +- 0.00031 | 0.01687 | -1.05 % | [0.015937, 0.017804] | sound | sound | True | +1.16 % ok | True |
| strut_bcc_R0.27_r0.06_nu0.342 | density | 0.19501 +- 7.8e-05 | 0.19511 | +0.05 % | [0.19503, 0.19514] | marginal | sound | False | n/a | n/a |
| strut_bcc_R0.27_r0.06_nu0.342 | nu100 | 0.45134 +- 0.0015 | 0.45343 | +0.21 % | [0.44509, 0.4617] | sound | sound | True | -0.37 % DIFF | n/a |
| strut_octet_r0.06_nu0.3 | E100 | 0.02762 +- 0.00052 | 0.027266 | -1.28 % | [0.026089, 0.028442] | sound | sound | True | +6.88 % ok | True |
| strut_octet_r0.06_nu0.3 | G | 0.018753 +- 0.00025 | 0.018412 | -1.82 % | [0.017571, 0.019253] | sound | sound | True | +6.00 % ok | True |
| strut_octet_r0.06_nu0.3 | bulk | 0.026898 +- 0.00062 | 0.026399 | -1.86 % | [0.025005, 0.027793] | sound | sound | True | +7.09 % ok | True |
| strut_octet_r0.06_nu0.3 | density | 0.15853 +- 0.00014 | 0.15819 | -0.21 % | [0.15755, 0.15884] | sound | sound | True | n/a | n/a |
| strut_octet_r0.06_nu0.3 | nu100 | 0.3288 +- 0.00085 | 0.32867 | -0.01 % | [0.32819, 0.32915] | marginal | marginal | True | +0.04 % ok | n/a |
| thin_sl_c0.402_w0.061_nu0.3 | E100 | 0.010727 +- 0.00026 | 0.010931 | +1.90 % | [0.010332, 0.012055] | sound | sound | True | -2.08 % ok | True |
| thin_sl_c0.402_w0.061_nu0.3 | G | 0.00032667 +- 3.2e-05 | 0.00022997 | -29.60 % | [-4.0909e-05, 0.00058171] | sound | sound | True | +16.00 % ok | True |
| thin_sl_c0.402_w0.061_nu0.3 | bulk | 0.0036377 +- 8.9e-05 | 0.0037083 | +1.94 % | [0.0035016, 0.0040968] | sound | sound | True | -2.12 % ok | True |
| thin_sl_c0.402_w0.061_nu0.3 | density | 0.27391 +- 0.00011 | 0.27392 | +0.01 % | [0.27388, 0.27395] | marginal | marginal | True | n/a | n/a |
| thin_sl_c0.402_w0.061_nu0.3 | nu100 | 0.0085455 +- 0.00019 | 0.00871 | +0.02 % | [0.0082437, 0.009573] | sound | sound | True | -0.02 % ok | n/a |
| thin_sl_c0.357_w0.109_nu0.3 | E100 | 0.021755 +- 0.00011 | 0.021817 | +0.28 % | [0.021097, 0.022945] | sound | sound | True | +1.24 % ok | True |
| thin_sl_c0.357_w0.109_nu0.3 | G | 0.00083741 +- 1.5e-05 | 0.00080904 | -3.39 % | [0.00062394, 0.0010614] | sound | sound | True | +12.09 % ok | True |
| thin_sl_c0.357_w0.109_nu0.3 | bulk | 0.0075429 +- 4.1e-05 | 0.0075648 | +0.29 % | [0.007305, 0.0079721] | sound | sound | True | +1.26 % ok | True |
| thin_sl_c0.357_w0.109_nu0.3 | density | 0.19793 +- 7.9e-05 | 0.19796 | +0.02 % | [0.19788, 0.19802] | marginal | sound | True | n/a | n/a |
| thin_sl_c0.357_w0.109_nu0.3 | nu100 | 0.019297 +- 9e-05 | 0.019345 | +0.00 % | [0.018724, 0.020302] | sound | sound | True | +0.01 % ok | n/a |

#### Gap edges (Q2-FCM reference over the refinement k subset; amm safe interval from the certificate)

| cell | nb | Q2 levels | R_lo +- 2u | R_hi +- 2u | amm ext (lo, hi) | delta ext | safe [s_lo, s_hi] | lo | hi | conservatism (lo, hi) | k coverage (dlo, dhi) | extreme k set (lo, hi) | band-index mismatch | earlier reference (levels: lo, hi) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tpms_schwarzp_d0.25_nu0.3 | 6 | [12, 16, 20] | 0.46410 +- 4.9e-04 | 0.83183 +- 3.3e-04 | (0.46435, 0.83157) | (+0.05 %, -0.03 %) | (0.47988, 0.82789) | sound | sound | (+3.4 %, +0.5 %) | (0.0e+00, 0.0e+00) | amm_path, own_adversarial | 0 | - |
| strut_bcc_R0.27_r0.06_nu0.342 | 12 | [12, 16, 20] | 0.34182 +- 1.9e-02 | 0.75964 +- 3.0e-02 | (0.33882, 0.72279) | (-0.88 %, -4.85 %) | (0.36772, 0.60146) | sound | sound | (+7.6 %, +20.8 %) | (5.0e-16, 1.1e-16) | own_adversarial, own_adversarial | 0 | - |
| thin_sl_c0.402_w0.061_nu0.3 | 6 | [24, 28, 32] | 0.10599 +- 6.3e-03 | 0.96465 +- 1.4e-02 | (0.11068, 0.96621) | (+4.43 %, +0.16 %) | (0.12058, 0.95117) | sound | marginal | (+13.8 %, +1.4 %) | (5.6e-15, 2.4e-15) | amm_path, own_adversarial | 0 | [16, 20, 24]: marginal, sound |
| thin_sl_c0.357_w0.109_nu0.3 | 6 | [16, 20, 24] | 0.19185 +- 7.6e-03 | 0.88119 +- 4.2e-02 | (0.19112, 0.88129) | (-0.38 %, +0.01 %) | (0.20247, 0.82270) | sound | sound | (+5.5 %, +6.6 %) | (1.1e-15, 0.0e+00) | own_adversarial, own_adversarial | 0 | - |

#### Per-k (gap cells)

| cell | sampled: amm n20 - Q2 n1, lo (% , min..max) | hi | extrapolated per-k max abs delta (lo, hi) | consistent |
|---|---|---|---|---|
| tpms_schwarzp_d0.25_nu0.3 | +1.09..+2.97 (45 k) | +0.32..+1.27 | (0.15 %, 0.02 %) | 9/9 |
| strut_bcc_R0.27_r0.06_nu0.342 | +1.21..+4.20 (45 k) | +4.26..+5.20 | (1.56 %, 5.15 %) | 8/8 |
| thin_sl_c0.402_w0.061_nu0.3 | -0.02..+6.14 (45 k) | +0.14..+0.57 | (30.62 %, 0.71 %) | 8/8 |
| thin_sl_c0.357_w0.109_nu0.3 | +0.38..+3.18 (45 k) | +2.60..+4.69 | (0.39 %, 0.06 %) | 8/8 |

#### Claims (nominal and marginal)

| cell | claim | key | target | independent status | amm margin |
|---|---|---|---|---|---|
| tpms_schwarzp_d0.25_nu0.3 | nominal | density_max | 0.26249 | agrees | +4.75 % |
| tpms_schwarzp_d0.25_nu0.3 | nominal | E100_min | 0.0673345 | agrees | +3.95 % |
| tpms_schwarzp_d0.25_nu0.3 | nominal | G_min | 0.0096245 | agrees | +2.15 % |
| tpms_schwarzp_d0.25_nu0.3 | nominal | nu100_min | 0.0329762 | agrees | +66.62 % |
| tpms_schwarzp_d0.25_nu0.3 | nominal | nu100_max | 0.0785527 | agrees | +27.98 % |
| tpms_schwarzp_d0.25_nu0.3 | nominal | gap | 0.48215-0.78766 | agrees | lo +0.47 %, hi +4.86 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | nominal | G_min | 0.0572056 | agrees | +5.90 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | nominal | density_max | 0.29 | agrees | +0.16 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | marginal | G_min | 0.0605782 | agrees | +0.01 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | marginal | density_max | 0.289526 | inconclusive | +0.00 % |
| strut_bcc_R0.27_r0.06_nu0.342 | nominal | G_min | 0.00407733 | agrees | +266.48 % |
| strut_bcc_R0.27_r0.06_nu0.342 | nominal | density_max | 0.21 | agrees | +7.08 % |
| strut_bcc_R0.27_r0.06_nu0.342 | marginal | G_min | 0.0149332 | agrees | +0.06 % |
| strut_bcc_R0.27_r0.06_nu0.342 | marginal | density_max | 0.195142 | agrees | +0.00 % |
| strut_bcc_R0.27_r0.06_nu0.342 | nominal | gap | 0.48874-0.55855 | agrees | lo +32.91 %, hi +7.13 % |
| strut_bcc_R0.27_r0.06_nu0.342 | marginal | gap | 0.37006-0.59912 | agrees | lo +0.64 %, hi +0.39 % |
| strut_octet_r0.06_nu0.3 | nominal | density_max | 0.165433 | agrees | +3.98 % |
| strut_octet_r0.06_nu0.3 | nominal | E100_min | 0.0256881 | agrees | +1.56 % |
| strut_octet_r0.06_nu0.3 | nominal | G_min | 0.0173976 | agrees | +0.99 % |
| strut_octet_r0.06_nu0.3 | nominal | nu100_min | 0.292097 | agrees | +12.36 % |
| strut_octet_r0.06_nu0.3 | nominal | nu100_max | 0.364949 | agrees | +9.81 % |
| thin_sl_c0.402_w0.061_nu0.3 | nominal | gap | 0.23144-0.63031 | agrees | lo +91.94 %, hi +33.73 % |
| thin_sl_c0.357_w0.109_nu0.3 | nominal | gap | 0.39158-0.44516 | agrees | lo +93.40 %, hi +45.89 % |
| thin_sl_c0.357_w0.109_nu0.3 | marginal | gap | 0.20867-0.81650 | agrees | lo +3.06 %, hi +0.75 % |

#### Band comparison (no-gap cells; bands 4-15 at G, X, M, R + 4 interior k; 1-15 off Gamma)

| cell | max abs delta (extrapolated, all) | consistent | rows with mode crossing | max abs delta (no crossing) | consistent (no crossing) | finest levels amm n40 vs Q2 n3, rel range | sampled amm n20 vs Q2 n1, rel range |
|---|---|---|---|---|---|---|---|
| tpms_schwarzp_sheet_d0.2895_nu0.342 | +26.79 % | 115/117 | 18 | +1.72 % | 99/99 | -26.83 %..+20.07 % | +0.41 %..+41.84 % |
| strut_octet_r0.06_nu0.3 | +17.45 % | 117/117 | 25 | +12.16 % | 92/92 | +0.57 %..+2.53 % | -0.78 %..+41.76 % |

#### Eigensolver-free band counts (PARDISO inertia at probe frequencies between clusters; deviation 8)

| cell | k checked | probes | Q2 Lanczos != inertia | amm-model Lanczos != inertia | count Q2 n3 != amm n40 |
|---|---|---|---|---|---|
| tpms_schwarzp_sheet_d0.2895_nu0.342 | flagged: amm_path:4, amm_path:16 | 7 | n12: 4 probes, Lanczos -3..-1 copies; n16: 4 probes, Lanczos -3..-1 copies; n20: 2 probes, Lanczos -3..-1 copies | n20: 3 probes, Lanczos -5..-1 copies; n30: 4 probes, Lanczos -3..-1 copies; n40: 3 probes, Lanczos -1..-1 copies | 0 |
| strut_octet_r0.06_nu0.3 | all 8 | 47 | 0 | n20: 2 probes, Lanczos -1..-1 copies | 21 probes (amm fewer modes below the probe in 21) |

#### Worst two-sided discrepancies (|delta|)

| cell | quantity | delta | consistent within 2 sqrt(u^2 + e^2) |
|---|---|---|---|
| thin_sl_c0.402_w0.061_nu0.3 | per-k lo at amm_path [0.0, 0.0, 0.0] | -30.62 % | True |
| thin_sl_c0.402_w0.061_nu0.3 | static G | -29.60 % | True |
| thin_sl_c0.402_w0.061_nu0.3 | per-k lo at own_adversarial [0.9982544674878416, 0.9980270866461951, 0.9978957956051929] | -13.75 % | True |
| thin_sl_c0.402_w0.061_nu0.3 | per-k lo at amm_path [1.0, 1.0, 1.0] | -13.75 % | True |
| thin_sl_c0.402_w0.061_nu0.3 | per-k lo at amm_path [1.0, 1.0, 0.0] | -11.51 % | True |
| strut_bcc_R0.27_r0.06_nu0.342 | per-k hi at amm_path [1.0, 1.0, 1.0] | -5.15 % | True |
| strut_bcc_R0.27_r0.06_nu0.342 | static E100 | -5.01 % | True |
| strut_bcc_R0.27_r0.06_nu0.342 | per-k hi at amm_path [1.0, 0.0, 0.0] | -4.88 % | True |
| strut_bcc_R0.27_r0.06_nu0.342 | gap hi edge (extrapolated) | -4.85 % | True |
| strut_bcc_R0.27_r0.06_nu0.342 | per-k hi at amm_path [0.0, 0.0, 0.0] | -4.85 % | True |

Bound/edge statuses: {'sound': 57, 'marginal': 11, 'unsound': 0}. Claim statuses: {'agrees': 23, 'inconclusive': 1, 'disagrees': 0}.

## Correction log (2026-11-08, after the mid-point Codex review `results/audit/midpoint_2026-11-08/report.md`)
- Section 1.3 prose for SL c.40 gap edges and section 1.4 uncertainty did not match the final
  reference in `T4_v1b.csv`. Corrected in place to the final `T4_v1b.csv` values: delta +4.43 % (lower) / +0.16 % (upper);
  final 2u of the lower edge about 6 %. Statuses (lower sound, upper marginal) and the verdict are unchanged.
