# Third-party Bloch solver (V1c), setup log

- 2026-11-07: pulled the official image `dolfinx/dolfinx:v0.11.0` (user approval 2026-11-07).
- Built dolfinx_mpc v0.11.0 (GitHub jorgensd/dolfinx_mpc, tag v0.11.0, commit 0302798d) in the image's
  complex-PETSc mode, using 4 cores. The build log is `build.log`; its only error is a version print in my own
  script.
- Committed the result as the local image `amm/dolfinx-mpc:0.11.0-complex`, sha256 4e56563aa6c5....
- Verified: dolfinx 0.11.0.post0, dolfinx_mpc 0.11.0, PETSc ScalarType complex128, MultiPointConstraint available.
- No solves until E4 phase 1 ends: the pre-registration allows no other solver work during E4.

Planned comparison (to run after E4):
- **Cells:**
  - the 5 certified gap cases (cube-and-bars, see `results/bench/NOTES.md` section 9);
  - 3 representative cells from V1b.
- **Model:** Q2 hexahedra on the same voxelized geometry at two resolutions, with Floquet-periodic constraints
  (complex scale e^{ik·a}) via dolfinx_mpc. SLEPc shift-invert at the same k-points (high-symmetry path plus the
  certificate's adversarial interior points).
- **Output:** two-sided discrepancies of the gap edges next to amm's certified edges and margins.

---

## V1c protocol (written 2026-11-07, before any DOLFINx-vs-amm number was computed)

Up to this point only these had been run: the homogeneous-solid sanity test (`sanity/`, DOLFINx against the
analytic folded dispersion; no amm involved) and the export of the cases (`inputs/`). The tolerances and the
acceptance rule below are fixed now and are not changed after the comparison numbers exist; any later deviation is
logged as such in a dated "Deviations" list.

**Code identity.** amm is imported only from the frozen E4 snapshot (`results/bench/e4/snapshot/source.zip`,
extracted to `C:\AI\AgenticMetamaterials_workspaces\v1c_frozen`; checker `f2e482d81382b400`, asserted by the scripts).
Reference values come from the stored certificates. The TPMS case has no stored certificate under this checker, so
its Bloch block is run once from the frozen code (`amm_cert.py`, shared solver lock).

**Cases (8).**
| Case | Source certificate | Role |
|---|---|---|
| cube_bars c 0.6 w 0.2, nu 0.342 | `results/verification/indep/cube_bars_c0.6_w0.2_nu0.342_amm.json` | certified gap case |
| cube_bars c 0.8 w 0.3, nu 0.3 | `.../cube_bars_c0.8_w0.3_nu0.3_amm.json` | certified gap case |
| cube_bars c 0.5 w 0.2, nu 0.3 | `.../cube_bars_c0.5_w0.2_nu0.3_g2_amm.json` | certified gap case |
| cube_bars c 0.6 w 0.3, nu 0.3 | `.../cube_bars_c0.6_w0.3_nu0.3_g2_amm.json` | certified gap case |
| cube_bars c 0.7 w 0.3, nu 0.3 | `.../cube_bars_c0.7_w0.3_nu0.3_g2_amm.json` | certified gap case |
| Schwarz P network, density 0.25, nu 0.3 (claim of the G2 gap reference) | `amm/tpms_schwarzp_d0.25_nu0.3_bloch.json` (frozen-code Bloch block) | TPMS |
| bcc struts R 0.27 r 0.06, nu 0.342 | E4 job codex-C-r1-A15, certificate `feceec63a345ee84_8306e070463fa197.json` | strut |
| sphere_ligaments c 0.402 w 0.0606, nu 0.3 (ligament at the calibrated thin limit) | E4 job codex-C-r1-G10, `40d98d0c519c50a5_f8934f3a9d393e14.json` | thin resonator |

**Third-party models** (`scripts/verify/dolfinx/bloch_dolfinx.py`, DOLFINx 0.11.0 + dolfinx_mpc 0.11.0, complex
PETSc/SLEPc, MUMPS; container `amm/dolfinx-mpc:0.11.0-complex`, at most 8 cores). Floquet constraints: dolfinx_mpc
geometric periodic constraints, one per wrap vector, complex scale exp(i k.w). Eigenvalues: SLEPc block subspace
iteration with shift-invert (Krylov-Schur missed copies of degenerate eigenvalues in the sanity test, which would
shift band indices), relative tolerance 1e-11.
- *exact* (cube-and-bars): the exact union of boxes on conforming tensor grids whose breakpoints include every face;
  Q2 at h about 1/10, 1/20, 1/30. Rayleigh-Ritz: each DOLFINx band is an upper bound of the continuum band at that k.
- *fcm* (curved cells): Q2 on amm's own voxel grid and sub-sample occupancy at n = 20, 30, 40 (the arrays amm meshes,
  exported by `export_cases.py`), partial cells integrated with 2x2x2 Gauss points on each sub-cube. The geometry is
  amm's discrete geometry, so a geometry-representation error shared by both codes is not tested on these cells.
- *identity*: Q1 with the midpoint rule on each sub-cube (the rule amm uses), n = 20, against amm's same discrete
  model with trilinear elements (`amm_bands.py id`). This isolates the Bloch implementation (phases, assembly, mass,
  eigen solve) from the element choice (amm certifies with hex8i, which DOLFINx does not provide).

**k-points.** S_amm = the certificate's 37 points (path kpath(4), interior ibz_interior(10, 0), the 6 adversarial
k). S_dfx = DOLFINx's own search at the coarsest level (path with 8 points per leg + 100 random interior points,
seed 20261107, then a 26-direction pattern search, 5 rounds, top 3 starts per edge), kept: the final 3 points per
edge. Levels n = 10 and 20 (exact) or 20 (fcm) evaluate S_amm and S_dfx; finer levels evaluate the 2 points per edge
that are extreme at the previous level plus Gamma, X, M, R.

**Edges and reference.** At each level, lo_D = max over evaluated k of band nb, hi_D = min of band nb+1 (nb = the
certificate's below_band). The reference uses the three levels on the same k-set (the finest level's): if the
sequence is monotone with shrinking steps, an order p is fitted (clipped to [0.5, 4]) and ext = E3 + d23 r,
u = max(|d23| r, 1e-4 E3), r = h3^p / (h2^p - h3^p); otherwise ext = E3, u = max(|d12|, |d23|).

**Acceptance rule, per edge** (amm safe interval [s_lo, s_hi] from the certificate):
- lower edge: *sound* if s_lo >= ext_lo + 2u_lo; *marginal* if ext_lo - 2u_lo <= s_lo < ext_lo + 2u_lo; *unsound*
  if s_lo < ext_lo - 2u_lo. On exact cells, additionally *rigorously sound at the sampled k* if s_lo >= lo_D(finest).
- upper edge: *sound* if s_hi <= ext_hi - 2u_hi; *marginal* within +-2u_hi; *unsound* if s_hi > ext_hi + 2u_hi. On
  exact cells, s_hi > hi_D(finest) is *unsound for certain* (above an upper bound of the true edge at that k).
- the claim [f_lo, f_hi] must lie inside [ext_lo + 2u_lo, ext_hi - 2u_hi] (reported per case).
- conservatism (reported, not pass/fail): c_lo = s_lo - ext_lo, c_hi = ext_hi - s_hi, and the fraction of the
  reference gap not certified, 1 - (s_hi - s_lo) / (ext_hi - ext_lo).
- k coverage: the DOLFINx extreme over S_amm and S_dfx against the extreme over S_amm alone, at each level; and amm's
  own model (`amm_bands.py cert`, n = 20, 30) at S_dfx against the certificate's edges. A more extreme k than amm
  sampled is reported with its size against amm's margin.

**Identity tolerance:** |f_D - f_amm| <= 1e-6 max(f_amm, 0.01) for bands 1 to nb+4 at every compared k; relative
eigen residuals <= 1e-8 on both sides.

**Gate verdict (npj CM):**
- *strong*: every identity test passes; no unsound edge; at most one marginal edge in the 16; every claim inside the
  reference interval; no DOLFINx k more extreme than amm's safe interval.
- *adequate*: identity passes and no unsound edge, but more than one marginal edge, or 2u larger than amm's margin
  on three or more edges (the comparison does not discriminate there).
- *weak*: any unsound edge, any identity failure, or any claim outside the reference interval.

Budget: at most about 6 h of container compute in total (8 cores); background runs for long jobs.

---

## V1c results (2026-11-07)

### Deviations from the protocol (dated 2026-11-07, each with when it was decided)

1. **Levels** (decided before any amm-vs-DOLFINx number). Q2 on the exact cube-and-bars geometry at n = 30 ran out
   of the 40 GB container memory on the densest cell (c 0.8, w 0.3; about 400k unknowns, 8 MPI ranks), and Q2 at
   n = 40 on the curved cells would be about 500k unknowns. Levels used: exact n = 10, 15, 20 (n = 10 and 15 on
   breakpoint-aligned, slightly non-uniform grids; for h in the fit see 9); fcm n = 16, 20, 30 (amm's own occupancy
   at each n). The two coarser levels evaluate S_amm and S_dfx, the finest the subset (2 extreme k per edge plus
   Gamma, X, M, R), as the protocol says for "finer levels".
2. **Eigen solver** (decided before any comparison number). SLEPc subspace iteration took about 200 s per k at
   118k unknowns, and Krylov-Schur missed copies of degenerate eigenvalues (sanity test). The production runs use a
   restarted block Krylov method on the shift-invert operator (PETSc/MUMPS LU, multi-RHS solves, block wider than any
   multiplicity; `block_eigs` in `bloch_dolfinx.py`), checked against dense LAPACK on the homogeneous cell (all 16
   bands, error <= 1e-12) and against SLEPc subspace iteration at the two edge k of every case (`*_slepc.json`).
3. **Serial fast path** (decided before any comparison number). In serial runs K and M are assembled once and each
   k applies K(k) = P^H K0 P with P built from dolfinx_mpc's own slave, master and coefficient data; equal to
   dolfinx_mpc.assemble_matrix to 1e-16 (relative, max entry) on the homogeneous and the thin-resonator cells. The
   finest level (all ranks on one k) and the SLEPc cross-check use dolfinx_mpc.assemble_matrix directly.
4. **Rigid-body modes in the identity metric** (decided after the first identity result). At Gamma the three
   rigid-body modes have lambda ~ 1e-14 in both codes, so f = sqrt(lambda) is round-off (up to 1.2e-7) and fails the
   1e-6 x 0.01 absolute floor of the rule as written. They are excluded from the frequency metric (they are not
   bands of the gap claim); the strict-letter value including them is reported in each case JSON. The amm-side
   reference eigen solver of the identity test (my harness, not amm) first stopped on eigenvalue change and left
   residuals of ~4e-7; it was changed to a residual stop (<= 1e-10) and the identity runs were repeated.
5. **Extra level at the edge k** (decided after the first case, c 0.5 w 0.2, showed an apparent order p = 0.47 and
   a large u on the upper edge). One finer level (exact n = 30, fcm n = 40) at only the two edge k of the finest
   level, where memory allowed. With it the protocol's own rule ("the three finest levels on the finest level's
   k-set") uses those levels; the three-level result without it is reported alongside (`coarse_reference`).
6. **Per-k extrapolation** (supplementary, decided after the first case). The rule fits the sequence of edges (max
   or min over the k-set). When the extreme k changes between levels (c 0.5 w 0.2: X at n = 10, 15; R at n = 20) the
   fitted order is distorted. Each k extrapolated separately, then the extreme over k, is reported as
   `per_k_reference`; verdicts are given by the pre-registered rule.
7. **Residual threshold**: the block solver stops at residual <= 1e-8 or on stagnation below 1e-7 (thin-ligament
   cells reach a floor of a few 1e-9 to 1e-8); the maximum residual per case is in the case JSON. For Hermitian
   pencils the eigenvalue error is of order the residual squared.
8. **Compute trims** (decided after the strut search took 44 min, before its comparison was computed): the last
   case (thin resonator) used a smaller search (40 random interior points, 3 rounds, top 2; 393 solves instead of
   921), and the finest fcm level evaluates 1 extreme k per edge plus Gamma, X, M, R (the strut case had already
   used 2 per edge). The extra level of deviation 5 was run only on the exact cells; on c 0.8 w 0.3 Q2 at n = 30
   ran out of memory again (killed at 40 GB), so that case keeps the levels 10, 15, 20. The SLEPc cross-check was
   skipped on the TPMS and strut cells.
9. **h in the order fit** (decided after the first extrapolations): h = 1/n (the nominal resolution) instead of the
   largest cell edge of the slightly non-uniform breakpoint grids, which jumps with rounding (0.125, 0.10, 0.05 for
   c 0.8 w 0.3 gave a fitted order 6.4 and an implausibly small u). The largest-cell-edge variant is kept in each
   case JSON (`hmax_reference`).
10. A harness slip at 16:55: a second and third copy of the pass-2 driver ran for about one minute in parallel
   (up to three containers, 24 cores) before I killed them and their containers; their partial outputs were not
   kept.
11. **amm's certificate model at S_dfx** (decided at 17:46, after it had run on c 0.5, c 0.6 w 0.2, c 0.6 w 0.3 at
   n = 20 and 30 and on c 0.7 at n = 20, all showing no k beyond the certificate edges). The n = 30 runs took 15 to 93
   min each on the CPU under the shared lock; the remaining n = 30 runs (c 0.7, c 0.8, TPMS, strut, thin) were
   stopped and those cells were run at n = 20 only.

### What was run

- `scripts/verify/dolfinx/`: `export_cases.py` (frozen amm geometry and certificate values -> `inputs/`),
  `amm_cert.py` (TPMS Bloch block, frozen code, lock), `bloch_dolfinx.py` (container side: meshes, dolfinx_mpc
  Floquet constraints, eigen solves, k search), `run_container.sh`, `run_case.py` / `run_all.sh` / `run_pass2.sh`
  (orchestration), `amm_bands.py` (amm identity model and certificate model at given k, frozen code, lock),
  `lock.py` (copy of the E4 lock protocol), `compare.py` (rule, JSON, CSV, figures; `--md` prints the table below).
- Sanity (`sanity/`): homogeneous solid against the analytic folded dispersion (Q2, n = 4: X-point transverse 0.50013
  vs 0.5; all 16 lowest bands equal a dense LAPACK solve of the same pencil to <= 1e-12; Hermitian to 1e-16).
  Krylov-Schur found 8 of the 12 degenerate modes at Gamma (`homog_q2_n4_krylovschur.json`), hence deviation 2.
- 7638 DOLFINx eigen solves: search 921 per case (393 thin), S_amm + S_dfx (41-43 k) at the two coarser levels,
  4-8 k at the finest, 1-2 k at the extra level; largest problem 294k unknowns (Q2, c 0.7 w 0.3, n = 30).
- Raw records: `raw/<case>/` (one JSON per level; `search.json`; `q1id_n20.json`; `*_slepc.json`); amm side:
  `amm/`; per-case results: `<case>.json`; `summary.csv`; figures `fig_<case>.png` (bands nb and nb+1 along the
  path and at the other k, per level, with amm's certificate edges, safe interval, claim and the DOLFINx reference
  band) and `fig_summary.png`.

### Results (pre-registered rule; reference = three finest levels on the finest level's k-set)

| Case | nb | claim | amm safe interval | DOLFINx finest [lo, hi] (n) | reference lo ± 2u | reference hi ± 2u | verdict lo / hi | gap not certified | identity max rel |
|---|---|---|---|---|---|---|---|---|---|
| cb_c0.6_w0.2_nu0.342 | 6 | 0.4428–0.6603 | 0.3324–0.6800 | 0.3208, 0.7029 (30) | 0.3191 ± 0.0034 | 0.6995 ± 0.0068 | sound / sound | 9 % | 2.6e-12 |
| cb_c0.8_w0.3_nu0.3 | 6 | 0.5032–0.5837 | 0.4383–0.5988 | 0.4174, 0.6026 (20) | 0.4156 ± 0.0036 | 0.6020 ± 0.0013 | sound / sound | 14 % | 3.4e-13 |
| cb_c0.5_w0.2_nu0.3 | 6 | 0.4126–0.5184 | 0.3796–0.5531 | 0.3587, 0.5685 (30) | 0.3584 ± 0.0007 | 0.5653 ± 0.0064 | sound / sound | 16 % | 1.4e-12 |
| cb_c0.6_w0.3_nu0.3 | 6 | 0.5693–0.6469 | 0.5543–0.6772 | 0.5284, 0.6841 (30) | 0.5262 ± 0.0045 | 0.6827 ± 0.0029 | sound / sound | 22 % | 4.1e-13 |
| cb_c0.7_w0.3_nu0.3 | 6 | 0.5192–0.6385 | 0.4984–0.6824 | 0.4575, 0.6971 (30) | 0.4543 ± 0.0062 | 0.6959 ± 0.0025 | sound / sound | 24 % | 3.4e-13 |
| tpms_schwarzp_d0.25_nu0.3 | 6 | 0.4822–0.7877 | 0.4799–0.8279 | 0.4646, 0.8315 (30) | 0.4646 ± 0.0019 | 0.8315 ± 0.0017 | sound / sound | 5 % | 1.6e-12 |
| strut_bcc_R0.27_r0.06_nu0.342 | 12 | 0.4887–0.5586 | 0.3677–0.6015 | 0.3497, 0.7712 (30) | 0.3497 ± 0.0042 | 0.7712 ± 0.0206 | sound / sound | 45 % | 1.9e-09 |
| thin_sl_c0.402_w0.061_nu0.3 | 6 | 0.2314–0.6303 | 0.1206–0.9512 | 0.1091, 0.9708 (30) | 0.1091 ± 0.0152 | 0.9707 ± 0.0003 | marginal / sound | 4 % | 1.0e-10 |

Columns:
- "DOLFINx finest" is lo_D and hi_D at the finest level. For the exact cells this is Q2 at n = 30 at the edge k; c 0.8 w 0.3 stops at n = 20 (see 8).
- "reference" is ext ± 2u from the three levels listed in `levels_reference` of the case JSON.
- "gap not certified" is 1 - (s_hi - s_lo) / (ext_hi - ext_lo).
- "identity" is the largest relative frequency difference between the Q1 midpoint-rule model and amm's same discrete model. It covers bands 1 to nb+4 at 6 k: Gamma, X, M, R, the first interior k and the first adversarial k. Rigid-body modes are excluded (deviation 4).

At the finest level every edge extreme sits at a symmetry point: Gamma, X or R.

The table below gives each margin in units of the comparison's own 2u. A margin is amm's safe edge minus the reference; positive means conservative.

| Case | c_lo | c_lo / 2u | c_hi | c_hi / 2u | order p lo / hi |
|---|---|---|---|---|---|
| cb_c0.6_w0.2_nu0.342 | 0.0133 | 3.9 | 0.0195 | 2.9 | 1.17 / 1.35 |
| cb_c0.8_w0.3_nu0.3 | 0.0228 | 6.4 | 0.0032 | 2.5 | 2.53 / 2.34 |
| cb_c0.5_w0.2_nu0.3 | 0.0212 | 30.7 | 0.0123 | 1.9 | 3.22 / 1.53 |
| cb_c0.6_w0.3_nu0.3 | 0.0282 | 6.2 | 0.0055 | 1.9 | 1.62 / 1.76 |
| cb_c0.7_w0.3_nu0.3 | 0.0441 | 7.1 | 0.0134 | 5.3 | 1.25 / 1.46 |
| tpms_schwarzp_d0.25_nu0.3 | 0.0153 | 8.1 | 0.0037 | 2.1 | not monotone / not monotone |
| strut_bcc_R0.27_r0.06_nu0.342 | 0.0180 | 4.2 | 0.1697 | 8.2 | not monotone / not monotone |
| thin_sl_c0.402_w0.061_nu0.3 | 0.0115 | **0.76** | 0.0195 | 61 | not monotone / 4 (clipped) |

"Not monotone" means the three levels do not form a monotone sequence with shrinking steps. The protocol's fallback then sets ext to the finest value and u to the largest change between levels. The fallback applies to at least one edge on each of the three curved cells. On those edges the reference is the n = 30 value, not an extrapolation.

### Secondary checks

- **Rigorous bounds on the exact cells.**
  - Q2 on the exact geometry is conforming, so each DOLFINx band is an upper bound of the continuum band at that k.
  - Lower edge: on all five cube-and-bars cells, amm's s_lo is at or above the largest value over the sampled k of the per-k smallest DOLFINx value of band nb. So the lower edge of the safe interval is rigorously sound at every sampled k (`rigorous_lo_sound_at_sampled_k`).
  - Upper edge: no s_hi exceeds an upper bound of band nb+1 (`rigorous_hi_unsound` is false). This check on its own is not rigorous, because it uses the extrapolation.
- **Claim.** Every claim [f_lo, f_hi] lies inside [ext_lo + 2u_lo, ext_hi - 2u_hi], and also inside the finest DOLFINx gap.
- **k coverage.**
  - DOLFINx ran its own search: the path with 8 points per leg, random interior points, then a pattern search. That is 921 solves per case and 393 on the thin cell.
  - The search found no k more extreme than amm's 37 points. At both levels that evaluate S_amm and S_dfx, the extreme over the two sets together equals the extreme over S_amm alone (d_lo = d_hi = 0 in all 8 cases).
  - amm's own certificate model (frozen code, `amm_bands.py cert`) evaluated at S_dfx is never beyond its certificate edges: at n = 20 on all 8 cells and at n = 30 on c 0.5, c 0.6 w 0.2 and c 0.6 w 0.3 (deviation 11), the extremes over S_dfx equal the certificate's edges to <= 2e-15 (thin upper edge: 1.1e-6 less extreme). On TPMS the safe lower edge equals amm's raw n = 20 edge, which this rerun reproduces to 1.7e-15; the first version of the check flagged that as 'beyond the safe interval', and `compare.py` now uses a 1e-12 relative tolerance.
- **Bloch implementation identity.** This compares Q1 with the midpoint sub-cube rule against amm's hex8 model, on the same occupancy at n = 20, with equal unknown counts (6018 to 16062).
  - Largest relative frequency difference, against a tolerance of 1e-6:
    - 3.4e-13 to 2.6e-12 on the cube-and-bars and TPMS cells;
    - 1.0e-10 on the thin cell;
    - 1.9e-9 on the strut cell, at the adversarial k near Gamma (0.0099, 0.0066, 0.0033) pi, where the acoustic bands have f of about 0.01.
  - The residual sub-criterion (at most 1e-8 on both sides) is not met by the letter:
    - amm-side residuals are at most 1e-10, except 3.2e-8 at the strut near-Gamma k and 5.9e-9 on c 0.8 at R.
    - DOLFINx-side residuals stop at the block solver's floor, at most 9.7e-8 (deviation 7).
  - For a Hermitian pencil the eigenvalue error is of order the squared residual. The 1e-12 agreement shows directly that this floor does not matter here.
- **Eigen solver cross-check.** SLEPc subspace iteration was run against the block solver at the two edge k of the second level.
  - The SLEPc run used shift-invert, MUMPS and dolfinx_mpc.assemble_matrix. The block solver used the serial fast path.
  - Largest relative difference in bands 1 to nb+4: 8e-14 to 8e-13 on the 5 cube-and-bars cells, and 5.3e-11 on the thin cell.
  - This check was not run on the TPMS and strut cells (deviation 8).
- **Residuals.**
  - Edge bands (nb and nb+1): the largest relative residual is at most 9.9e-8 in every case.
  - Other bands go up to 2.4e-6 (c 0.6 w 0.3), 3.3e-6 (TPMS) and 4.8e-5 (strut). These are acoustic bands 1-2 near Gamma at the fcm n = 30 level, which hit the iteration limit. They do not enter any edge.
- **amm raw edges against the reference.**
  - amm's own finest raw edges (n = 40, hex8i + FCM) lie 0.2 to 1.8 % above the DOLFINx reference. At n = 20 and 30 they lie 0.4 to 7.3 % above it. So amm's discretisation converges from above toward the third-party value.
  - The certificate's three-resolution fit, with safety factor 2, moves the safe edges past the reference in all 16 edges. One of them clears it by less than 2u.
  - On c 0.7 w 0.3 the amm lower edge at n = 30 is 6.4 % above the reference, which is further than at n = 20 (4.1 %). amm's edge guard handles this non-monotone sequence with its own fallback.
- **Conservatism.**
  - amm leaves 4 to 24 % of the reference gap uncertified on seven cells.
  - On the bcc strut cell it leaves 45 %. Its upper safe edge (0.6015) is far below the reference upper edge (0.7712, 2u = 0.021). amm's guard on that edge is loose by about 8 times the comparison's own uncertainty.

### Variants

These are reported for information. The verdicts follow the rule above.

| Variant | marginal edges | unsound edges |
|---|---|---|
| final rule (levels with the extra level of deviation 5, h = 1/n) | 1 (thin lo) | 0 |
| coarse three levels (the levels as first planned, no extra level) | 4 (thin lo; c 0.5, c 0.6 w 0.3, c 0.7 hi) | 0 |
| h = largest cell edge | 2 (thin lo, c 0.5 hi) | 0 |
| per-k extrapolation (deviation 6) | 1 (thin lo) | 0 |

### Verdict for the venue gate: adequate

[Corrected 2026-11-08: the literal pre-registered verdict is WEAK because the identity residual criterion fails;
see the correction log at the end.] Read with the logged deviations and setting the residual sub-criterion aside,
the remaining gate criteria would give *strong*:
- No unsound edge in the 16.
- One marginal edge: the thin resonator's lower edge, with a margin of 0.0115 against 2u = 0.0152.
- Every claim lies inside the reference interval and inside the finest third-party gap.
- No third-party k is more extreme than amm's safe interval.
- The Bloch implementation agrees to 1e-12 (strut 2e-9).

I rate it **adequate**, not strong, for four reasons:

1. The count that makes it strong depends on deviations 5 and 9. I decided both after the first comparison numbers existed. With the levels as first planned, 4 edges are marginal, which is adequate by the rule. No variant has an unsound edge, so the soundness finding is robust. The "at most one marginal edge" finding is not.
2. The identity test does not meet the residual part of its own tolerance by the letter: the DOLFINx side reaches about 1e-7 (deviation 7). The frequencies still agree 5 to 6 orders of magnitude inside the tolerance.
3. On the three curved cells, DOLFINx runs on amm's own voxel occupancy (the fcm model). There the check tests the element, quadrature, Bloch and eigen implementations and the convergence in n. It does not test amm's geometry representation (sub-sample occupancy of the implicit surface), because both codes share it. On these cells the reference is the n = 30 value with u taken from the change between levels, not an extrapolation.
4. On the exact cells only the lower edge is checked rigorously (Rayleigh-Ritz). The upper edge rests on extrapolating upper bounds. Its smallest margins are 1.9 to 2.5 times 2u (c 0.5 w 0.2, c 0.6 w 0.3, c 0.8 w 0.3).

What the comparison establishes:
- The check covers 8 cells and 16 edges. An independent code (DOLFINx + dolfinx_mpc) uses different elements, quadrature, constraint construction and eigen solver from amm.
- That code finds every amm safe interval inside its own converged gap.
- On all five exact-geometry cells the lower edge is rigorously inside the gap at the sampled k.
- amm's Floquet implementation matches the third-party one to round-off on the same discrete model.

What the comparison does not establish:
- Soundness at k that neither code sampled. Both codes rely on sampling; DOLFINx's denser search found nothing beyond amm's points.
- Geometry fidelity on implicit-surface cells.

### Compute

- DOLFINx containers (`--cpus 8`, `--memory 40g`):
  - 4.97 h in the steps that were kept;
  - about 5.3 h including the failed out-of-memory attempts and the one-minute duplicate;
  - about 0.4 h more of sanity and timing tests;
  - about 5.7 h in total.
  - 7638 eigen solves in all. The largest problem had 293,754 unknowns.
- amm side (frozen code, CPU, under the shared lock): about 3.6 h wall (certificate model at S_dfx about 3.1 h including one stopped n = 30 run; identity model about 0.5 h). The TPMS Bloch block ran on the GPU in 331 s.

### Unresolved

- **c 0.8 w 0.3 stops at n = 20.** Its exact-geometry levels go no finer than n = 20, because Q2 at n = 30 needs more than 40 GB. Its reference uses the three coarser levels. Its upper-edge margin (0.0032, 2.5 x 2u) is the smallest absolute margin of the exact cells.
- **Thin resonator lower edge is marginal** (0.76 x 2u). The reference there is the n = 30 value, because the fcm sequence is not monotone. A finer fcm level (n = 40, about 500k Q2 unknowns) would settle it; it was not run.
- **Curved cells share amm's discrete geometry.** An independent geometry, such as a body-fitted mesh of the implicit surface, was not available in the image. It was not attempted, because no downloads were allowed.
- **Identity residuals reach only about 1e-7.** The identity residual sub-criterion is met only to about 1e-7 on the DOLFINx side (deviation 7).
- **amm's certificate model at DOLFINx's k ran at n = 30 on three cells only** (deviation 11).
- **The 8-core limit was briefly exceeded.** For about one minute, three pass-2 drivers ran in parallel by accident (deviation 10).

## Correction log (2026-11-08, after the mid-point Codex review `results/audit/midpoint_2026-11-08/report.md`)
- **Literal pre-registered gate verdict: WEAK.** The gate above makes any identity failure "weak", and identity
  requires relative eigen residuals <= 1e-8 on both sides. DOLFINx-side residuals reach 9.7e-8 (deviation 7), so
  the identity test fails by the letter. `compare.py` `identity.passed` checks frequency agreement only, which is
  why summary.csv shows True.
- **Qualified assessment: adequate.** Frequencies agree to <= 2e-9 relative (far inside 1e-6), and for Hermitian
  pencils the eigenvalue error is of order the residual squared. Edge classes under the amended procedure: 15 sound,
  1 marginal, 0 unsound; under the originally planned levels: 4 marginal, 0 unsound. Deviations 5 and 9 were
  decided after first comparison numbers existed; deviation 7 has no clear decision timestamp.
- Report both the literal verdict and the qualified assessment in the paper; do not call the registered gate passed.

---

## Addendum 2026-11-10: exact-geometry references for two engineering cells (V18)

Not part of the V1c protocol or its verdict. After the audit asked for references independent of amm's voxel
geometry, the same pipeline (`run_case.py` steps search, l1, l2, l3, l4; container and solver unchanged) was run on
the two cube-and-bar engineering cells: `eng_mount_cb_c0.592_w0.151` (certificate 7db650ec44d50a1d) and
`eng_316L_cb_c0.787_w0.06` (finer gap check, results/verification/v15). Inputs were written by
`scripts/experiments/v18_dolfinx_engineering.py export` from the live amm k sets (the certificates' 37 k), not from the
frozen E4 code; no amm-side step was run. The mount's cubic moduli come from long-wavelength acoustic speeds at
|k| = 0.05 pi and 0.1 pi (Q2, n = 10, 15, 20, 30; n = 30 one k per container after a 4-rank run failed). Judged with
`compare.extrapolate` / `classify_*` on the three finest levels. Results: results/verification/v18/references.json.
