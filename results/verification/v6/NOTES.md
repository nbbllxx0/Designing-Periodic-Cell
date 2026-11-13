# V6: engineering cases with acceptance tests

Plan item V6 (`plan/SOFTWARE_PAPER_PLAN.md` section 5, claim S4; table T7, figures F7 and F8). Scripts:
`scripts/verify/v6/`. Code: amm 0.2.0, tool contract amm-tools/3, profile C (full system), no LLM.

## 0. Status of this file

Sections 1-6 were written on 2026-11-08 **before any V6 design, certificate, chain, macro or recheck run**. Only
these had run when they were written:
- `select_spec.py` and a faster re-scan of the same oracle (search atlas + calibrated error model; no solve), used
  to place the targets (section 1.3, `spec_selection.json`);
- `selftest_fe.py`: the new finite-mesh FE module on homogeneous solids with analytic answers
  (`selftest_fe.json`: uniaxial-strain column exact to 2e-15; harmonic rod T(f) within 3e-7 at f* = 0.02 and
  converging O(h^2) near resonance);
- a smoke test of the STL re-voxelizer on a throw-away export of an atlas cell (scratchpad, not a result).
Thresholds and rules below are not changed after results exist; any later change goes to section 7
(Deviations) with its date and reason.

## 1. Case 1: vibration-isolation mount (main case)

### 1.1 Requirement (stated)

| item | value |
|---|---|
| material | PA12 by SLS (amm.units.MATERIALS: E_s = 1.70 GPa, nu_s = 0.39, rho_s = 1010 kg/m^3, typical minimum feature 0.8 mm) |
| cell size | a = 20 mm |
| mount | block of 6 x 6 x 6 cells (120 x 120 x 120 mm) between two rigid steel plates bonded to its top and bottom faces; loading axis z = cube axis [001] |
| static load | W = 1.8 kN compressive, uniform through the top plate; bottom plate fixed |
| stiffness | deflection delta <= 0.25 mm under W, i.e. k = W / delta >= 7.2 kN/mm |
| isolation band | complete elastic-wave band gap covering 11.5-14.95 kHz (structure-borne noise; a ratio f_hi/f_lo = 1.3) |

**Frequency range.** Bragg/local-resonance gaps of 20 mm polymer cells lie at tens of kHz (c_t a^-1 = 38.9 kHz per
unit f*). This is a structure-borne-noise isolation band, not low-frequency machine-vibration isolation (< 1 kHz),
which would need cells of 0.2 m or heavy resonator masses. The case is stated in these terms.

### 1.2 amm spec

`set_material PA12`; `set_constraints cell_size 20 mm`; `set_target E100_min = 60 MPa, gap [11500, 14950] Hz`,
`gap_type complete`. Normalized: E100_min = 0.03529 E_s; gap f* = [0.29558, 0.38426].
E100_min follows from the stiffness requirement by the uniaxial-stress estimate k = E100 A / H (lateral faces free,
frictionless plates): E100_min = k_req H / A = 7.2e6 N/m x 0.12 m / 0.0144 m^2 = 60 MPa. The bonded plates stiffen
the block (lateral constraint near the plates), so the requirement in E100 is conservative; the macro solve
(section 1.4) checks the real block.

### 1.3 How the numbers were chosen (atlas, before any solve)

Rule written before the scan: W, delta and the mount geometry first; then the band [f_lo, 1.5 f_lo] with the lowest
f_lo on a 0.5 kHz grid whose atlas oracle is FEASIBLE with 3 <= n_clear <= 20 (n_clear = atlas cells that clear
every target at the pessimistic end of the calibrated search-tier error ranges: "feasible but not trivial").
First attempt (W = 3 kN, delta 0.25 mm -> E100_min = 100 MPa, ratio 1.5): **no** f_lo was FEASIBLE (all BORDERLINE or
NOT_FOUND; `spec_selection.json`). Re-scan over E100_min in {60, 80, 100} MPa and band ratio in {1.2, 1.3, 1.4, 1.5}
(n_clear per f_lo, same error model): at 100 MPa nothing clears; at 80 MPa only ratio 1.2-1.3 with n_clear <= 2; at
60 MPa ratio 1.3 clears from f_lo = 8.5 kHz with n_clear 1-4. Chosen: E100_min = 60 MPa (W = 1.8 kN, delta 0.25 mm),
ratio 1.3, the lowest f_lo with n_clear >= 3: **f_lo = 11.5 kHz, n_clear = 3**. These are search-tier
estimates; only the certificate decides.

### 1.4 Workflow (library Session, the GUI and agent calls)

`scripts/verify/v6/case1_session.py`, under `scripts/ops/gpulock_run.py v6`:
set_material -> set_constraints -> set_target -> set_source (stated) -> check_bounds -> atlas_suggest(top 5) ->
evaluate(the 5, bands=True) -> certify the suggestions **in atlas_suggest order until one is certified, at most 3
certify calls** (rule fixed now) -> submit(release) -> screen_manufacturing(tiles 3, resolution 64) ->
export(tiles 3, resolution 64, tile_resolution 32) -> get_session. Log: `case1/session_design/session.jsonl`;
then `amm.tools.replay` of that log (must be exact; result in `case1/replay_design.json`).
If no design is certified within 3 calls, the case is reported as failed at A1 with the certificates' reasons; the
targets are not changed.

### 1.5 Reference design (rule fixed now)

Same material and cell size, no complete gap in the band, similar static stiffness. Candidates: atlas cells at
nu = 0.39 of the strut and TPMS families whose search-tier rows have no complete gap (rel >= 1 %) overlapping
[f_lo, f_hi]. Pick the candidate whose atlas E100 is closest to the **evaluate** (search-tier) E100 of the certified
design; ties to TPMS. Session `case1/session_reference`: PA12, 20 mm, target E100_min = 60 MPa only; evaluate ->
certify -> submit(release) -> export. A4 (below) needs its macro stiffness within +-10 % of the design's; if it
fails, the next candidate by the same order is taken (at most 3), recorded. Its complete-gap status is from evaluate
(search tier); a directional (normal-incidence) stop band of the reference, if the chain shows one, is reported.

### 1.6 Macro static check (`macro.py`, CPU)

- **C\*** from the certificate's guarded values: cubic tensor from E100 = guarded **lower** E100, G = guarded **lower**
  G, and nu100 at its guarded lower and upper bound (two solves; the smaller stiffness is reported). Normalized by
  E_s, scaled by E_s in Pa.
- Homogenized block 6 x 6 x 6 cells (cell units, a = 1), hex8i elements (amm.fem.hex8_ke with the anisotropic D),
  m = 2, 4, 8 elements per cell edge. Bottom face u = 0; top face u = (0, 0, -delta) bonded rigid plate; lateral faces
  free. k = reaction / delta; physical k = k* E_s a; predicted deflection under W: W / k. The finest m is reported;
  its change from the next coarser m is reported (expected < 1 %).
- **Direct voxel check:** a finite 3 x 3 x 3-cell voxel block of the certified geometry (amm.geometry.design_cell,
  finite-cell partial voxels, amm.fem elements; cut cells at the free lateral faces, plates bonded to the cell faces
  at z = 0 and z = 3a), n = 16 and 24 voxels per cell, same plates. Compared with the homogenized 3 x 3 x 3 block
  using the certificate's extrapolated E100, G, nu100 (estimate vs estimate) and with the guarded C\*.
- **Size-effect caveat:** homogenization assumes many cells; at 3 and 6 cells the cut surface cells and the plate
  boundary layers change the stiffness. The 3x3x3 voxel/homogenized ratio is reported, and a size-corrected 6x6x6
  deflection (homogenized x the 3x3x3 ratio when it is below 1) is reported next to the requirement (flag A2s; it is
  reported, not a pass/fail gate, because the ratio at 3 cells overstates the size effect at 6 cells).

### 1.7 Finite-chain transmission (`chain.py`, CPU)

- **Model:** 6 cells stacked along z (loading axis), voxel FE of the certified geometry (design_cell: coverage +
  finite-cell sub-samples, hex8i full voxels, consistent mass), linear elasticity.
- **Transverse boundary:** periodic in x and y (Bloch k_perp = 0): the chain is an infinite periodic slab 6 cells
  thick. **Consequence:** it tests normal incidence along [001] only (the Gamma-X direction, all three
  polarizations), whereas the certified complete gap covers every direction and polarization; oblique incidence,
  finite lateral size and mode conversion at a finite mount's edges are not tested.
- **Excitation:** a rigid plate bonded to the input face z = 0 drives every node of that face with displacement
  U0 = 1 along the drive direction (and zero in the other two): longitudinal (z) and shear (x) drives, solved with
  one factorization per frequency. Output face z = 6a: traction free.
- **Transmission:** T(f) = |u_out(f)| / U0, where u_out is the solid-area-weighted mean over the output-face nodes
  of the complex displacement component along the drive direction (lumped face area of the solid top-layer elements).
  T -> 1 (0 dB) as f -> 0. Reported in dB: 20 log10 T.
- **Damping:** hysteretic, K\* = (1 + i eta) K, loss factor eta = 0.01, all elements, frequency independent. Mass
  undamped.
- **Solver:** real symmetric 2N form of the complex symmetric system, MKL PARDISO (mtype -2), symbolic factorization
  reused over frequencies; relative residual and perturbed pivots recorded per frequency.
- **Frequencies:** 41 equally spaced f in [f_lo, f_hi] (the band metric) plus 120 equally spaced f* in
  [0.01, 1.5 f*_hi] (the figure).
- **Mesh convergence:** n = 16 and n = 24 voxels per cell (sub-samples s = 6 and 4, amm's rule). Reported: band-mean
  T_dB per design and drive at both n, and their difference.
- Same model for the reference design.

### 1.8 Acceptance tests, Case 1 (thresholds fixed now)

| id | test | pass if |
|---|---|---|
| A1 | certification | a design certified (verdict "certified") for E100_min = 60 MPa and the complete gap 11.5-14.95 kHz, released by submit; the log replays exactly |
| A2 | macro stiffness | homogenized 6x6x6 deflection with the guarded C\* (worst nu100), finest mesh: delta <= 0.25 mm under 1.8 kN |
| A2s | size effect (reported flag) | size-corrected deflection <= 0.25 mm (reported, not a gate) |
| A3 | 6-cell transmission | band-mean of T_dB over the 41 band frequencies: design minus reference <= **-20 dB**, for BOTH drives and at BOTH resolutions. If the verdict differs between n = 16 and 24, A3 is "undetermined (mesh)" |
| A4 | reference validity | reference certified for E100_min = 60 MPa; its macro stiffness (same rule as A2) within +-10 % of the design's; no complete gap (search tier) overlapping the band |
| A5 | exported geometry | the exported cell.stl, re-voxelized independently (section 3), meets the spec under amm's own guards: guarded lower E100 >= E100_min and the full gap count + edge guard passes for the claim. Differences from the certificate reported regardless |

Screening (`screen_manufacturing`, `export`): reported in T7, not an acceptance test (screening is not a
printability claim).

## 2. Case 2: filter cell (secondary)

- **Requirement:** a complete gap covering **35-42 kHz** (ratio 1.2) with a **10 mm** cell, in PA12 (SLS) and in
  316L (LPBF: E_s = 193 GPa, nu_s = 0.30, rho_s = 8000 kg/m^3, minimum feature 0.3 mm). Gap only (no stiffness target).
- **Normalized:** PA12 f* = [0.4498, 0.5398]; 316L f* = [0.1149, 0.1379]: the same physical band is a factor
  c_t(316L)/c_t(PA12) = 3.91 lower in f* for the steel, so the two materials need different normalized designs
  (c_t a sets the scale; nu_s differs too, 0.30 vs 0.39, so even equal f* bands are different problems).
- **Chosen by:** scan of ratios 1.1-1.25, f_lo on a 2.5 kHz grid, both materials at a = 10 mm; first ratio-1.2 band
  with n_clear >= 1 in both: f_lo = 35 kHz (n_clear 3 and 3). At ratio 1.25 no common band exists in the atlas.
- **Workflow per material** (`case2_session.py`, one session per material, `case2/session_PA12`,
  `case2/session_316L`): as in 1.4 (certify in atlas_suggest order, at most 3 certify calls), then screen and export,
  then replay.
- **Acceptance:** F1 certified in each material; F5 exported-geometry recheck as A5 (gap claim only; density and
  E100 differences reported). Reported, not tested: whether the two certified designs differ, and their screening
  flags against each process's minimum feature.
- **Scaling check (optional, if compute allows):** the PA12 design certified for 316L at the cell size that maps the
  f* band exactly (a = 10 mm x 3.91 = 39.1 mm): it tests c_t a scaling with a changed nu_s. Reported only.

## 3. Exported-geometry recheck (`recheck.py`; Cases 1 and 2)

- Input: `exports/<name>/cell.stl` (mm) written by `export` (marching cubes of the level-set field at resolution 64).
- Re-voxelization (`stl_recheck.py`, written for V6; trimesh is not installed, scikit-image is not used here): ray
  parity along z on an (n s)^3 sample grid (jittered by ~1e-6 a), coverage = sample mean per voxel, sub-samples
  passed to amm's finite-cell elements; cleaned to the largest periodic component. Independent resolutions:
  static n = 32, 48, 64 with s = 5, 3, 3 (the certificate: s = 3, 2, 2 at 32, 48, 64 on the analytic field);
  Bloch n = 20, 30 counted (s = 5, 5), n = 40 edges (s = 3); grid phases by translating the sample grid (periodic
  wrap of the sample positions into the closed cell STL): static phases 0 and 0.5 voxel at every n; Bloch phases
  0.25 and 0.5 at n = 30. (Odd s so that a half-voxel phase moves the samples; edited before any recheck ran: the
  first draft had s = 4, 3, 2 and 5, 4, where a 0.5-voxel phase reuses the same sample points.)
- Static: amm.homog.homogenize on every mesh; amm.certify.static_convergence (the certificate's guard) on the STL
  rows -> guarded bounds; amm.certify.static_verdict for the spec.
- Gap: amm.bloch.certify_gap with the certificate's k set (kpath(4), 10 interior, seed 0) plus the certificate's
  adversarial k AND a fresh GPU adversarial search on the STL mesh at n = 10 (amm.bloch.adversarial_ks, seconds);
  edge meshes n = 40 and phase meshes as above. Verdict by amm.certify.gap_verdict.
- Differences from the certificate at matched resolution: density, E100, G, nu100 (phase 0 at n = 32, 48, 64), the
  guarded bounds, and the gap edges at n = 20, 30, 40.
- **Cap:** GPU use only for the adversarial search (well under the 30 GPU-minute cap); the rest is CPU PARDISO.

## 4. Compute rules

All runs that touch the GPU (sessions, certify, evaluate, recheck) go through `python scripts/ops/gpulock_run.py v6
-- <cmd>`; CPU-only FE (macro, chain) runs without the lock with MKL_NUM_THREADS <= 16. Long runs are kept awake with
`scripts/ops/keep_awake.py <pid>`. Wall-clock times are recorded per run (`*_timing` fields, T7 column `time`).

## 5. Outputs

`case1/`, `case2/` (sessions, certificates, exports, replay, recheck, macro, chain JSON), `T7_v6.csv`,
`fig_v6_mount.png` (F8), `fig_v6_gallery.png` (F7). Figures are data plots from these files only.

## 6. Chain solver placement

`scripts/verify/v6/finite_fe.py` is standalone: it reuses amm.geometry, amm.fem and amm.pardiso without changing
them. Whether it should move into amm is assessed in section 9 after the runs.

## 7. Deviations

1. **2026-11-08, reference ranking (before the reference was selected or evaluated; the design session was running,
   no certificate existed yet).** Section 1.5 ranks candidates by raw atlas E100. Search-tier stiffness bias differs
   by family (median +4 % resonators, +12 % struts, +2.5 % TPMS; results/atlas/error_model.json), so raw values would
   systematically pick a too-soft strut reference. Changed to |E100_corr - E100_corr(design)| with E100_corr = atlas
   E100 / (1 + family median error) (`select_reference.py`). The +-10 % macro-stiffness test A4 is unchanged.
2. **2026-11-08, size-effect ratio (after the first design macro run).** Section 1.6 compared the 3x3x3 voxel block
   with the homogenized 3x3x3 block built from the certificate's *extrapolated* C\*. The first run gave a ratio of
   1.07, but that mixes the finite-size effect with discretization bias: the voxel block at n = 16, 24, 32 is a
   single-phase sequence (0.1314, 0.1274, 0.1271 E_s a) that looks converged while the certificate's phase-averaged
   ladder extrapolates E100 about 6 % lower (the effect amm.certify's docstring warns about). Added (`macro.py`): the
   periodic cell's own C\* at the same n (amm.homog, phase 0) in the same 3x3x3 plate solve; the matched ratio is
   the size-effect estimate (design: 1.017, 1.015, 1.012 at n = 16, 24, 32) and A2s now uses it at n = 32. Both
   ratios are kept in `macro_*.json`. A2s is a reported flag; its value did not change (ratio > 1 -> no correction),
   A2 is unaffected.
3. **2026-11-08, STL re-voxelization anti-aliasing (after the first static rows of the design recheck, before any
   recheck verdict).** Section 3 specified binary ray-parity samples. On the flat-faced cube_bars cell the binary
   samples aliased with the grid phase: STL density 0.2310 / 0.2385 (n = 32, phases 0 / 0.5), 0.2388 / 0.2321
   (n = 64), E100 0.04225 / 0.04008 at n = 64 (5 % phase spread, above amm's 5 % static tolerance), i.e. the
   recheck tool's own sampling noise, not the STL. Changed to anti-aliased fine-cell fractions
   (`stl_recheck.coverage_grid`): the exact inside length along rays in x, y and z through each fine-cell centre,
   averaging the directions that see a partial value. Test on the same STL: density 0.2371 / 0.2371 (n = 32) and
   0.2371 / 0.2370 (n = 64) at phases 0 / 0.5; mean |coverage - amm field coverage| 0.0015-0.0021 (binary:
   0.0029-0.0053). The aborted binary run's rows are kept in `case1/recheck_design_binary_aborted.log`; it reached no
   verdict. The certificate's own geometry model is anti-aliased too (amm.geometry), so this matches like with like.

4. **2026-11-08, case-1 sessions rerun under one code identity (after all case-1 results existed; told by the
   coordinator).** amm's code identity changed while V6 ran (V2 added amm/cli.py and fixed amm/tools.py, edits at about
   07:30, 07:31 and 07:58 by file times; V6 changed nothing in amm/). The first case-1 design and reference sessions
   were written by code e0350cf7efa454b0; every later run (case 2, the scaling check, the GUI walkthrough, all
   replays) by f1a6d625064a6d18; the checker hash c5f8c89871b3bad6 is the same throughout. Replayed under the current
   code, the old design log was not bit-exact (certify static bounds and E100_MPa differ at <= 5.6e-14 relative,
   evaluate C entries at the round-off level, the export report bytes follow) and the old reference log differed only
   in the export report's sha256. The case-1 design and reference sessions were therefore rerun with the same configs
   and rules (`queue_rerun_case1.sh`), replayed, and the checks that read their certificates (macro, recheck) rerun.
   The old runs are kept in `case1/archive_code_e0350cf7/`. The chain results were kept: they depend only on the
   design spec and amm.geometry / amm.fem (covered by the unchanged checker hash), not on the certificate values;
   the exported STLs of the rerun are byte-identical (same sha256) to the first ones.
5. **2026-11-08, shared GPU lock (reported by the coordinator).** `scripts/ops/gpulock_run.py` released the lock
   with an unconditional unlink until it was fixed during V6, so an exiting holder could delete another process's
   lock: V2 (PID 29476) and V6 processes 50636 and 28208 held the solver at the same time around 08:33 and again
   during V2's pytest. `recheck.py` imports the same GpuLock class, so V6's rechecks that ran before the fix could
   have done the same. Effect on results: none expected (concurrent GPU/CPU use changes timing, not the numbers; the
   replays of the case-2 sessions are bit-exact), but **every timing measured before V2 finished (about 09:40) is
   inflated by contention** for CPU and GPU: the first case-1 sessions, the chains, macro runs, rechecks, case-2
   sessions and replays, and the GUI walkthrough. Only the case-1 rerun (deviation 4) ran without V2 contending.

## 8. Results (2026-11-08)

All numbers below are read from the result files named; T7_v6.csv collects them (`build_t7.py`).

### 8.1 Case 1: mount

**Workflow (A1).** `case1/session_design` (`summary.json`, `session.jsonl`, `certificates/`, `exports/`).
check_bounds FEASIBLE (n_clear 3); atlas_suggest #1 cube_bars c = 0.592174, w = 0.151304 (search tier: E100 72.5 MPa,
gap 11.0-31.8 kHz); **certified on the first certify call** (first run 307 s under contention: static 62 s, Bloch 231 s, as-built 15 s; rerun 304 s), static
rung (32, 48, 64): guarded E100 >= 0.037505 E_s = **63.76 MPa** (target 60, margin +6.3 %); density <= 0.2360; gap
claim f* [0.2956, 0.3843] inside the **safe interval f* [0.2643, 0.6579] = 10.28-25.60 kHz** (margins 11.8 % below
f_lo, 71 % above f_hi), band index 6. As-built +-0.01 a (0.2 mm): dilation passes; **erosion fails E100** (54.4 MPa <
60; gap counts hold) -> robust = false (a flag, reported). submit(release) -> outcome certified_candidate.
Screening: passed (min solid feature 2.19 mm vs 0.8 mm, narrowest channel 5.31 mm, 3x3x3 block connected, both
STLs watertight). Export cube_bars_7db650ec_08d264 (cell.stl 23,564 triangles; tiled 137,916).
**A1: PASS** (certified and released). Replay: see 8.4. All case-1 numbers in 8.1 are from the rerun under code
f1a6d625 (deviation 4); they equal the first run's to the digits printed.

**Reference (A4).** `reference_selection.json`: 1,461 strut/TPMS atlas cells without a gap overlapping the band;
the first three by |E100_corr - 0.04091| were octet (r 0.0448, R 0.2545), octet (r 0.0591, R 0.2), bcc. Certify
#1 (octet r 0.0448): **undetermined** after climbing to rung (64, 80, 96) (guarded E100 lower 0.0317 < 0.0353; rerun 637 s, first run 769 s).
Certify #2: **octet r = 0.05913, R = 0.2 certified** (rerun 98 s, first run 118 s), guarded E100 >= 61.85 MPa, nu100 0.319-0.330, G >= 40.3
MPa. Search tier: no complete gap (`evaluate`). Macro stiffness 8.097 kN/mm vs design 7.654: **+5.8 %**.
**A4: PASS** (certified, within +-10 %, no complete gap). Its Gamma-X search-tier bands show a *directional* shear
stop band around 11.2-13 kHz (transverse branches end at 11.2 kHz at X; the next branches start near 13.2 kHz),
which is why its shear transmission in the band is -26 to -30 dB (below).

**Macro static check (A2, A2s).** `macro_design.json`, `macro_reference.json`.
- Homogenized 6x6x6 block, guarded C\* (E100 lower, G lower, worst nu100), bonded plates: design k = **7.654
  kN/mm**, deflection **0.2352 mm** under 1.8 kN (requirement <= 0.25 mm, margin 6.3 %); mesh change m = 4 -> 8:
  -1e-5. Uniaxial estimate E100 A/H = 7.651 kN/mm: the bonded plates add only 0.04 % because nu100 = 0.04 for this
  cell. Reference: 8.097 kN/mm, 0.2223 mm (plates add 9 % over E100 A/H; nu100 = 0.32). **A2: PASS** (both).
- Direct voxel 3x3x3 block (n = 16, 24, 32; up to 0.89 M dof design, 1.13 M dof reference): design k\* = 0.13136,
  0.12737, 0.12714 E_s a. Against the homogenized 3x3x3 block with the periodic cell's own C\* at the same n: ratio
  **1.017, 1.015, 1.012** (design), **1.008, 1.007, 1.007** (reference): the finite 3x3x3 block with bonded plates is
  ~1 % *stiffer* than the homogenized prediction; no softening size effect at 3 cells for this load case. Against
  the certificate's extrapolated C\* the ratio is 1.07 (design): that is the discretization bias of a single-phase
  voxel sequence, not size (deviation 2). **A2s: PASS** (size-corrected deflection 0.2352 mm; ratio > 1, so no
  correction).
- **Size-effect caveat.** Homogenization assumes scale separation; at 3-6 cells the cut cells at the free lateral
  faces and the plate boundary layers matter. Here they stiffen by ~1 % at 3 cells under axial compression. Other
  loads (shear, tilting, lateral load) were not checked, and the design's shear modulus is very low (guarded
  G >= 2.49 MPa, Zener ~0.1): the mount's lateral stiffness is far below its axial stiffness, so it needs lateral
  guidance in service. Strength, buckling of the bars, PA12 creep and contact were not checked (linear elasticity
  only; mean stress 0.125 MPa).

**6-cell transmission (A3).** `chain_{design,reference}_n{16,24}.json`. Periodic slab, k_perp = 0, eta = 0.01,
driven bonded plate, free end. Free dof 30,708 / 97,740 (design n = 16 / 24), 45,720 / 116,712 (reference); 161
frequencies each; max relative residual 7.6e-13; no perturbed pivots. Band mean of T_dB over the 41 frequencies in
11.5-14.95 kHz:

| drive | n | design | reference | design - reference |
|---|---|---|---|---|
| longitudinal | 16 | -79.3 dB | +5.5 dB | **-84.9 dB** |
| longitudinal | 24 | -81.7 dB | +7.2 dB | **-88.9 dB** |
| shear (x) | 16 | -102.8 dB | -25.6 dB | **-77.2 dB** |
| shear (x) | 24 | -110.9 dB | -29.7 dB | **-81.2 dB** |

Worst case inside the band (design): -60.7 / -63.4 dB longitudinal, -80.5 / -91.6 dB shear (n = 16 / 24).
Mesh change 16 -> 24: design -2.4 dB (long.) and -8.1 dB (shear); reference +1.6 dB and -4.1 dB; the verdict is the
same at both resolutions. **A3: PASS** (threshold -20 dB; every case passes by more than 57 dB).
Observations (not tests): the design's longitudinal attenuation starts at ~9 kHz, below the certified safe edge
10.28 kHz, because the normal-incidence (Gamma-X) stop band is wider than the complete gap; the design also has a
directional shear stop band at 3.5-6 kHz. In-band levels of -80 to -110 dB are those of an ideal periodic 6-cell
model; finite lateral size, oblique incidence, flanking paths, manufacturing variation and measurement noise floors
are not modelled and would dominate in practice. Shear convergence (8 dB between n = 16 and 24) is not tight; only
the -20 dB comparison is claimed.

**Exported geometry (A5).** `recheck_design.json` (anti-aliased STL re-voxelization, deviation 3).
STL vs certificate: density +0.54 % (0.2371 vs 0.2358; the marching-cubes surface at 64 per edge adds material),
E100 extrapolated +1.3 % (0.03987 vs 0.03936 E_s); at matched resolution (phase 0) E100 +2.1, +2.3, +2.9 % at n =
32, 48, 64; G +4 to +7 % (G not targeted, not converged on the STL ladder). STL guarded E100 >= 0.036934 E_s = **62.8
MPa** >= 60 -> static certified. Gap on the STL geometry: inertia counts pass at every k at n = 20 and 30 (path,
interior, the certificate's adversarial k and a fresh adversarial search on the STL), edge guard passes, **safe
interval 10.50-24.87 kHz** (certificate 10.28-25.60) -> gap certified. Edges at matched n: lower edge +0.9 % (n 20)
to +2.0 % (n 30, 40), upper edge +0.2 to +1.4 %. **A5: PASS**; the emitted file meets the spec with smaller margins
(E100 +4.7 % instead of +6.3 %; lower gap edge 9.5 % below f_lo instead of 11.8 %). Reference STL
(`recheck_reference.json`): density -0.53 %, E100 +1.05 %, guarded E100 >= 64.3 MPa -> certified.

**GUI walkthrough (optional, F2 material).** `scripts/verify/v6/gui_case_mount.py`, live GUI (headless Edge over
CDP, port 8768), every step through the browser UI: same spec -> check_bounds FEASIBLE -> atlas suggestion #1
(cube_bars c 0.592, w 0.151) -> evaluate -> certify -> release -> screen -> export. The GUI certificate equals the
script's (certified, guarded E100 63.759 MPa, safe interval f* [0.2643, 0.6579]). Screenshots
`paper/figures/gui_case_mount_{1_spec,2_evaluate,3_certified,4_export}.png` (caption band added); record
`case1/gui_walkthrough.json` (2,121 s wall, mostly waiting for the shared solver lock).

### 8.2 Case 2: filter cell

| | PA12, a = 10 mm | 316L, a = 10 mm |
|---|---|---|
| normalized claim | f* 0.4498-0.5398 | f* 0.1149-0.1379 |
| check_bounds / n_clear | FEASIBLE / 3 | FEASIBLE / 3 |
| certified design (1st certify call) | sphere_ligaments c 0.356522, w 0.108696 | cube_bars c 0.786957, w 0.06 |
| certify time | 600 s | 973 s |
| safe interval | 16.51-66.14 kHz | 30.49-175.79 kHz |
| as-built robust | true | false (dilation fails the gap counts) |
| screening | **failed**: min solid 0.74 mm < 0.8 mm SLS limit (ligament diameter 1.09 mm; voxel 0.16 mm) | passed: min solid 1.41 mm vs 0.3 mm |
| STL recheck | gap certified, safe 16.12-68.27 kHz; density -0.27 %, E100 -3.2 % | gap certified, safe 29.66-176.73 kHz; density -0.93 %, E100 +1.5 % |

**F1: PASS** in both materials. **F5: PASS** in both (gap re-certified on the exported geometry). The two
materials need **different designs**: the same physical band is a factor 3.91 lower in f\* for the steel, and the
workflow moves from a PA12 sphere-and-ligament resonator to a steel cube-and-bar resonator with 0.6 mm bars. The
PA12 design passes the certificate but **fails manufacturing screening** at the stated SLS minimum feature; this is
reported, not tuned (screening is not part of certification; a user would bound the ligament width from below and
re-certify).

### 8.2b Case 2 scaling check (optional)

`case2/session_scaling_316L`: the certified PA12 filter design (sphere_ligaments c 0.356522, w 0.108696) in 316L at
a = 39.148 mm (= 10 mm x c_t(316L)/c_t(PA12), so the 35-42 kHz band maps to the same f* 0.4498-0.5398). **Certified**
(370 s, robust), safe interval f* [0.2025, 0.8227] = 15.75-64.01 kHz, versus f* [0.2122, 0.8500] at nu_s = 0.39 in
PA12: the normalized edges move by -4.6 % / -3.2 % with nu_s 0.39 -> 0.30, and the claim stays inside. Screening
passed (min solid 2.91 mm vs 0.3 mm). So the same normalized design carries over by c_t a when the cell may grow to
39 mm, with a nu_s-dependent shift that a certificate must re-check; at a fixed 10 mm cell the two materials need
different designs (8.2). Not an acceptance test.

### 8.3 Acceptance summary

| test | result | numbers |
|---|---|---|
| A1 certification (mount) | PASS | certified on call 1; E100 >= 63.76 MPa (target 60); safe gap 10.28-25.60 kHz (claim 11.5-14.95) |
| A2 macro stiffness | PASS | 0.2352 mm <= 0.25 mm under 1.8 kN (k 7.654 kN/mm, guarded C\*) |
| A2s size effect (flag) | PASS | 3x3x3 voxel / homogenized at same n = 1.012 (n 32): no softening; corrected 0.2352 mm |
| A3 transmission | PASS | design - reference band mean -84.9 / -88.9 dB (long., n 16 / 24), -77.2 / -81.2 dB (shear) vs -20 dB |
| A4 reference | PASS | octet r 0.0591 R 0.2 certified (E100 >= 61.85 MPa) on call 2 (call 1 undetermined); k +5.8 % |
| A5 exported geometry (mount) | PASS | STL: density +0.54 %, E100 +1.3 %, guarded E100 62.8 MPa, gap safe 10.50-24.87 kHz |
| F1 filter certification | PASS / PASS | PA12 sphere_ligaments, 316L cube_bars (different designs) |
| F5 filter exported geometry | PASS / PASS | gap re-certified on both STLs |
| replay (8.4) | exact | 4/4 acceptance sessions replay bit-exactly under the single code f1a6d625 |
| screening (reported) | 4 of 5 passed | PA12 filter design fails the 0.8 mm SLS feature limit (0.74 mm) |

### 8.4 Replay and code identity

`amm.tools.replay` (bit-exact) plus a tolerance comparison on the same re-executed calls (`replay_session.py`).
Every session the acceptance tests rely on (`case1/session_{design,reference}`, `case2/session_{PA12,316L,
scaling_316L}`, the two GUI sessions) now carries the single code identity **f1a6d625064a6d18** (checker
c5f8c89871b3bad6) in its session.jsonl header, and every replay ran under that same code:
- Mount design (`case1/replay_design.json`) and reference (`case1/replay_reference.json`), rerun sessions
  (deviation 4): **exact**, 15/15 calls each, tolerance comparison max relative difference 0.
- PA12 filter (`case2/replay_PA12.json`) and 316L filter (`case2/replay_316L.json`): **exact**, 14/14 calls.
- The scaling session was not replayed (not an acceptance test).
- First case-1 sessions (code e0350cf7, archived in `case1/archive_code_e0350cf7/`): replayed under f1a6d625 they
  were not bit-exact. Design: 3 of 15 results differ (evaluate C entries at the round-off level, certify static
  bounds up to 5.6e-14 relative, e.g. E100_MPa 63.758969102414476 -> 63.75896910241373, and the export report bytes
  that print those digits). Reference: only the export report's sha256. Every verdict, outcome, design and released
  design agreed. The rerun under f1a6d625 reproduces the replayed values exactly (the GUI certificate, also written
  by f1a6d625, gives the same E100_MPa 63.75896910241373), and the rerun reference certificate equals the archived
  one bit for bit (E100 61.85430286672436 MPa). So the change came from the amm code edit, not from solver
  nondeterminism; V6 did not diff the old tools.py (no copy kept).
- Downstream: macro numbers from the rerun certificates equal the archived ones to the printed digits (design k
  7.653944533944 vs 7.653944533946 kN/mm; reference identical; size ratios identical); the chains do not read the
  certificate; the rechecks were rerun (8.1 A5 numbers are from the rerun).
- Note for amm (corrected 2026-11-08 after the final asset audit, results/audit/final_assets_2026-11-08/report.md
  finding 5): the certificate JSON embeds the checker hash (e.g. `checker: c5f8c89871b3bad6` in
  case1/session_design/certificates/7db650ec44d50a1d_08d26401ae0bf0dc.json) but not the tool-code hash; the session
  log header records the tool-code identity. Keep both for complete session provenance. (The earlier text said the
  certificate carried no code or checker hash; that was wrong for the checker.)

### 8.5 Compute

Wall times (`seconds` fields). Timings measured before about 09:40, while V2 was using the GPU lock and CPU
(deviation 5), are **inflated** and marked (c); the case-1 rerun ran alone. Lock-held runs (sessions, replays)
include their CPU solves.
- Case-1 sessions, rerun (alone): design 323 s (certify 304 s), reference 758 s (certify 637 s undetermined + 98 s).
  First runs (c): 327 s (307) and 913 s (769 + 118), i.e. contention added ~0-20 %.
- Case-2 sessions (c): PA12 627 s (certify 600), 316L 995 s (973), scaling check 389 s (370).
- Replays: case-1 rerun design 324 s, reference 757 s; case 2 (c) PA12 1,041 s, 316L 982 s; first-code case-1
  replays (c) 586 s design + tolerance replay, 933 s reference.
- GPU work proper: search-tier evaluate (6-10 s per session) and the adversarial k searches inside certify and in
  the rechecks (seconds each); well under 10 GPU-minutes in total. The first rechecks' `gpu_seconds` fields (c,
  519-1,847 s) were mostly waiting for the shared lock, not GPU use.
- CPU only (no lock, MKL <= 16 threads): chains (c) 134 + 675 + 252 + 751 s; macro rerun 63 + 76 s (first runs (c)
  86 + 180 s); rechecks, case-1 rerun (alone) design 305 s, reference 31 s (first runs (c) 1,160 s and 77 s);
  case 2 (c) PA12 2,782 s, 316L 2,518 s (mostly lock waits inside the GPU k search).
- GUI walkthrough (c): 2,121 s wall (certify job 1,947 s, mostly lock waits).
- Total elapsed for V6: about 4.5 h including queueing behind V2 and the case-1 rerun (~1.2 h).

## 9. Limitations

- The chain is an infinite periodic slab at normal incidence (k_perp = 0): it tests Gamma-X propagation only, all
  three polarizations; oblique incidence, a finite lateral size, mode conversion at the mount's edges and flanking
  paths through fixtures are not tested. The complete gap is a property of the infinite lattice (certificate).
- Ideal model: linear elasticity, frequency-independent hysteretic damping eta = 0.01, rigid bonded plates, nominal
  material data from amm.units (not measured), no manufacturing variation. In-band levels below about -60 dB have
  no practical meaning beyond "strongly attenuated".
- Mesh: chain at n = 16 and 24 only (two resolutions; shear band means move 4-8 dB between them); the conclusion holds
  at both, the levels are not converged.
- Static: axial compression only; no lateral, shear or tilting load, no strength, buckling, creep or fatigue check.
  The mount design is very compliant in shear (guarded G >= 2.5 MPa).
- The mount design is not robust to a 0.2 mm erosion (E100 drops to 54 MPa < 60); the 316L filter design is not
  robust to a 0.1 mm dilation (gap count fails). Both are flags, not verdicts.
- Exported-geometry recheck: one STL resolution (export default 64 per edge); the recheck uses amm's own solvers on
  an independently voxelized geometry (not an independent solver).
- Requirements were placed with the search atlas (section 1.3) so that they are feasible; frequency bands are
  structure-borne-noise bands (kHz), set by c_t a.
- Screening is not a printability claim; the PA12 filter design fails it.

## 10. Should the finite-mesh solver move into amm?

Yes, as an optional verification module (e.g. `amm.finite`), not as part of the certificate. `finite_fe.py` is
~330 lines on top of amm.geometry / amm.fem / amm.pardiso, passed analytic self-tests (`selftest_fe.json`), and gave
results consistent with the homogenized and Bloch models here (stop bands where the bands say, 3x3x3 blocks within
1-2 % of homogenization at the same n). Moving it would let the GUI and the agent run a stated transmission and
macro-stiffness check after a certificate. Before moving: unit tests in tests/ (the self-tests), a tool contract entry
(new schema version, results clearly labelled "model check, not a certificate"), a job-time bound (n = 24 chain:
~11 min CPU) and documentation of the boundary model. The STL re-voxelizer (`stl_recheck.py`) is a candidate for
`amm.export` as an optional "recheck exported file" step.

## 11. Files

- `NOTES.md` (this file), `spec_selection.json`, `spec_rescan.json` / `.log`, `selftest_fe.json`, `T7_v6.csv`,
  `fig_v6_mount.png` (F8), `fig_v6_gallery.png` (F7), `queue_gpu*.log`.
- `case1/`: `config_design.json`, `config_reference.json`, `reference_selection.json`, `session_design/`,
  `session_reference/` (session.jsonl, summary.json, certificates/, exports/), `session_*.log`,
  `macro_{design,reference}.json/.log`, `chain_{design,reference}_n{16,24}.json/.log`,
  `recheck_{design,reference}.json/.log`, `recheck_design_binary_aborted.log`, `replay_{design,reference}.json/.log`,
  `archive_code_e0350cf7/` (first case-1 sessions, macro, rechecks and replays under code e0350cf7), `gui_walkthrough.json/.log`, `gui_sessions/`.
- `case2/`: `config_{PA12,316L,scaling_316L}.json`, `session_{PA12,316L,scaling_316L}/` and logs,
  `recheck_{PA12,316L}.json/.log`, `replay_{PA12,316L}.json/.log`.
- Scripts `scripts/verify/v6/`: `select_spec.py`, `rescan_spec.py`, `finite_fe.py`, `selftest_fe.py`,
  `run_session.py`, `select_reference.py`, `macro.py`, `chain.py`, `stl_recheck.py`, `recheck.py`,
  `replay_session.py`, `figures.py`, `build_t7.py`, `gui_case_mount.py`, `queue_gpu.sh`, `queue_gpu3.sh`,
  `queue_rerun_case1.sh` / `queue_rerun_case1b.sh` (rerun; the first was stopped after its second job and continued
  one job at a time by the second to keep MKL threads <= 16), logs `queue_rerun_case1.log`.
- GUI screenshots: `paper/figures/gui_case_mount_{1_spec,2_evaluate,3_certified,4_export}.png`.
