# V3: search benchmark (held out, budget-matched, no LLM)

Protocol written 2026-11-07 18:19 PST (PST timestamps throughout), **before any benchmark run, before the target
draw and before the timing pilot**. The text of sections 1-9 is frozen; later changes go only into the dated
"Deviations" list (section 10), each marked as decided before or after any result was seen.

Feeds the venue gate in `plan/SOFTWARE_PAPER_PLAN.md` (claim S3, evidence row V3, section 8 row V3). No LLM, CLI or
API is called. Scripts: `scripts/verify/v3/`. Outputs: this folder. `amm/` is not edited.

## 1. Held-out check (done before writing this protocol)

Question: was any witnessed confirmatory E4 spec used to tune search hyperparameters, the error model or the atlas?

- **Atlas** (`results/atlas/atlas_nu*.jsonl`, written 2026-11-04 15:53-19:24) and **error model**
  (`results/atlas/error_model.json`, 2026-11-04 16:54; fitted on 73 cells: the 50 G2 cells, 11 phase-ladder
  cells, 12 thin-end cells, `results/atlas/calibration*.json`) predate the benchmark plan
  (`bench/v1/plan.json`, 2026-11-05 08:50). They cannot have been fitted on any E4 spec.
- **Search hyperparameters** (q = 8, n_cand = 1024, max_arms = 3, objective "expected", 3-point Sobol start per
  unseeded arm) were set in week 3 on 14 G2 claims (`results/atlas/NOTES.md` section 5, gate step 3). `amm/search.py`
  equals the E4 plan-time snapshot (`results/bench/e4/snapshot/source.zip`, 2026-11-06 21:40, before any
  confirmatory session) except for the B3 change of the import block into an optional-extra guard (no logic change;
  B3 reports 132/132 bit-identical reference outputs).
- **Certificate guards** were tuned on G2 cells (week 2) and the development partition (pilot, near-miss);
  confirmatory specs were only scored (frozen checker), not used to change code.
- Result: **no confirmatory spec was used for tuning; none is excluded.**
- **Construction bias, not tuning (stated as a limitation):** every witness is an atlas grid cell, and the targets
  were derived from that cell (`scripts/bench/build.py`): "easy" targets at 0.80 x the median-corrected atlas value
  (the same error-model medians the BO's "expected" objective uses), "hard" targets from the witness's certified
  bounds at 0.97-0.995 x. So an atlas row that meets each target exists by construction. This favours methods that
  read the atlas (atlas-only, BO with seeding, ablation 6) over methods that do not (Sobol, DE, ablation 5).

## 2. Targets

Pool: the **42 witnessed confirmatory specs** (E4 confirmatory partition of `results/bench/e4/jobs.json`,
`truth.certificate == "certified"`, one entry per `scoring.spec_key`; for an ambiguous pair, the non-ambiguous
brief's record). Targets = `truth.normalized` (normalized by E_s; gap in f* = f a / c_t); Poisson ratio = the
material's (316L 0.3, Ti6Al4V 0.342, PA12 0.39). Pool strata (witness family x target type: static / gap /
combined): resonator 8/9/9, struts 6/3/4, TPMS 3/0/0.

**Primary draw (20 targets), rule fixed here:**
1. Strata = (witness family, target type), 7 non-empty strata.
2. Quota per stratum = 20 x n_stratum / 42; floor; at least 1; the remaining slots go to the largest remainders;
   ties in remainder broken by `numpy.random.default_rng(20261108)` (one permutation of the tied strata).
3. Within each stratum (specs sorted by brief id), draw the quota without replacement with the same generator,
   strata processed in sorted order.
4. Processing order of the 20 = one permutation by the same generator (used for the compute cut in section 7).

**Calibration-check targets (reported separately, not in any test):** from the 22 undrawn specs, 2 at nu = 0.342
and 2 at nu = 0.39, drawn with the same generator after step 4 (specs sorted by brief id within each nu). They
run only methods 4 and 6 (full BO and BO without error correction), since the question there is whether the
error correction fitted at nu = 0.3 (`results/atlas/NOTES.md` section 7) transfers. A second calibration check
uses every certificate of the run: per Poisson ratio, the observed search-tier error e = search/extrapolated - 1
(E100, G, bulk) and the gap-edge shifts, against the error model's median and range.

Note: the primary 20 contain targets at all three Poisson ratios; results are also broken down by nu
(descriptive only).

## 3. Methods (one seed each: seed 0; same design space, evaluator, budget and batch size)

Design space: all three families, 13 arms (4 TPMS kinds x {network, sheet}, sc / bcc / octet struts, cube_bars and
sphere_ligaments resonators), the boxes of `amm.atlas.BOX`, the parameter mapping `amm.search.to_spec` (struts:
node-sphere snap) and validity rule `amm.atlas.valid`. Evaluator: `amm.evaluate.evaluate_batch(specs, nu,
keep_bands=True, **amm.atlas.SEARCH_TIER)` (static n = 20, Bloch n = 10, 4 points per leg, 24 eigenvalues; the
same call the search tool makes), in batches of 8. **Budget: 48 new search-tier evaluations** (the default of
`amm.search.search`, and the budget of the E4 no-LLM reference arm O; the tool's own default is 32).

Objective for selection: the **"expected"** slack (search-tier values corrected by the error-model medians,
`amm.atlas.slacks(..., "expected")`), the default of amm's search, for every method except ablation 6. Using it in
the baselines too means the comparison isolates the search strategy; the value of the correction itself is
ablation 6. Final design of every method = its best design by its objective among everything it saw.

1. **Atlas-only (M1):** the atlas row (same nu) with the highest expected slack. 0 new evaluations.
2. **Sobol (M2):** a scrambled Sobol sequence in 3-D (`scipy.stats.qmc.Sobol`, seed 0): u0 picks the arm
   (floor(13 u0)), u1 (and u2 for 2-D arms) the parameters; points that fail the validity rule are skipped (not
   evaluated, not counted), the first 48 valid points are evaluated.
3. **Differential evolution (M3):** `scipy.optimize.differential_evolution` (scipy 1.15.3, installed; `cma` is not
   installed and is not installed for this), variables (arm index as integer via `integrality`, u1, u2),
   population 8 (initial population = the first 8 points of the Sobol design above, after projection), 5
   generations (8 + 5 x 8 = 48 evaluations), `updating="deferred"`, `vectorized=True` (one batch per generation),
   `polish=False`, `tol=0`, `atol=0`, default mutation (0.5, 1) and recombination 0.7, seed 0, minimizing the
   negative expected slack. Invalid points are projected (cube_bars w := min(w, c - 0.04); sphere_ligaments
   w := min(w, 2c - 0.02); struts by `to_spec`). Unused budget, if DE stops early, is reported.
4. **Full BO (M4):** `amm.search.search(targets, nu, budget=48, q=8, objective="expected", seed=0,
   atlas_rows=<atlas at nu>)`, i.e. exactly the `search` tool's call (atlas seeding of the GPs and of the arm
   choice, error correction, qLogEI). Final design = `best[0]` (may be an atlas row).
5. **BO without atlas seeding (M5):** as 4 with `atlas_rows=None` (all 13 arms, 3-point Sobol start each, then BO).
6. **BO without error correction (M6):** as 4 with `objective="nominal"`.

## 4. Certificate rule (same for every method)

- The final design is certified iff its **nominal** search-tier slack is > 0 (every target met by the raw
  search-tier values). Otherwise it is a **failure without a certificate**. (Search-tier values converge from
  above for stiffness and both gap edges, so a nominal miss on a minimum target is almost never certifiable.)
- `amm.certify.certify(spec, targets, nu=nu, as_built=False)` with every other setting at its default (the
  current checker; the as-built flag is not required for release and is off, as in the benchmark build).
- Identical final designs (same spec hash, same target, same nu) share one certificate (computed once); each
  method still counts one certification call and the full certificate time in its workflow time.
- **Certified success** = certificate verdict "certified". Refuted, undetermined and uncertified all count as
  failure.

## 5. Metrics (per target x method; `runs.csv`)

- certified success (primary);
- target slack: search-tier nominal / expected / pessimistic slack of the final design, and the **certified
  slack** (minimum over targets of the relative margin of the guarded bound: static min (lower - t)/|t|, max
  (t - upper)/|t|; gap min(f_lo - safe_lo, safe_hi - f_hi)/f_mid on the certificate's safe interval);
- search-tier evaluations spent, and **evaluations to the final design** (1-based index of the evaluation that
  produced it; 0 when it is an atlas row);
- certification calls (0 or 1 per method; plus unique certificates computed);
- times, reported separately: **throughput** (search-tier evaluations per second of search wall time),
  **response latency** (wall time of one search call, i.e. the time to the final design), **certificate time**,
  and **workflow time** (search + certificate, end to end). Timing is wall clock in one process at a time on the
  RTX 4090 / i9-13900KF; search processes use MKL_NUM_THREADS = OMP_NUM_THREADS = 4 with the search tier's 4
  static workers (16 threads), certificate processes 16 MKL threads.
- best-so-far curves: per method and evaluation count, the fraction of targets whose best design so far has
  expected slack > 0 and nominal slack > 0 (figure F5, with the certified-success points at the final budget).

## 6. Statistics and the "clear advantage" definition (fixed here, before any run)

- Unit: the target (paired across methods). n = 20 primary targets.
- **Primary family** (M4 vs M1, M2, M3): exact two-sided McNemar test (binomial on discordant pairs) of certified
  success, Holm-adjusted over the 3 comparisons. 95 % CIs of the paired success-rate differences by bootstrap
  over targets (10,000 resamples, seed 20261108).
- **Cost:** C = evaluations to the final design for a certified success, 48 (the budget) for a failure. Paired
  two-sided sign-flip permutation test of the mean per-target difference (all 2^n flips if n <= 20, else 100,000
  random), Holm over the 3 baselines; bootstrap CI.
- **Secondary (descriptive, Holm over 2):** M4 vs M5 and M4 vs M6, same tests.
- **"Best baseline"** = the baseline with the highest certified-success count (all tied baselines if tied).
- **Clear advantage of the BO pipeline** if (A) or (B):
  - (A) M4's certified-success count is higher than the best baseline's, and the Holm-adjusted McNemar p against
    the best baseline (each one if tied) is < 0.05; or
  - (B) M4's certified-success count is >= the best baseline's, M4's mean C is <= 50 % of the best baseline's,
    and the Holm-adjusted sign-flip p for C is < 0.05.
- **Baseline better** if some baseline satisfies (A) or (B) against M4 with the roles exchanged.
- **No clear advantage** otherwise.
- **Detectable effect at n = 20:** McNemar needs >= 6 discordant pairs all in one direction for p < 0.05
  (6:0, p = 0.031) and >= 7 for p < 0.0167 (the first Holm step; 7:0, p = 0.016; 8:1 gives p = 0.039). Simulated
  power (4,000 draws): a true difference of 30 points (40 % discordant pairs, 7:1 split) is detected with power
  0.28 at alpha 0.0167 and 0.45 at 0.05; 40 points (50 % discordant, 9:1) with 0.50 / 0.69. So only a large
  advantage (about 40-50 points) is reliably detectable; a null result does not exclude a moderate effect.

## 7. Compute plan and pre-registered cut rule

- Cap 15 h wall in total (target 10-15 h). One certificate is timed first on a **development** witness (not a
  V3 target), and the 6 methods are timed on one development spec, before the full run; the estimate is written
  to section 10 before the full run starts.
- If the estimate exceeds 15 h, cut in this order until it fits, before starting: (1) drop the calibration-check
  targets; (2) drop ablation 6 (M6); (3) reduce the primary targets to the first 16 in processing order.
- During the run (targets in processing order, calibration targets last): after each target, if elapsed time +
  (mean time per finished target x targets left) exceeds 15 h, apply the next cut of the same list from that
  point on (a dropped method is dropped for every target, its finished rows reported as exploratory only).
- GPU work runs under `scripts/ops/gpulock_run.py`; the machine is kept awake with `scripts/ops/keep_awake.py`;
  rows are written as they finish and the runner resumes from them.

## 8. Forward-solver comparison against the external tool

From the existing V1 files only (`results/verification/dolfinx/`, `results/verification/v1b/`), nothing rerun:
accuracy (band-edge and stiffness differences) and runtime of amm against DOLFINx-MPC on identical cells.
Output: `forward_vs_dolfinx.md`.

## 9. Deliverables

`targets.json`, `runs.csv`, `certs/`, `summary.json`, `T5_v3.csv`, `fig_v3_success_vs_budget.png`,
`forward_vs_dolfinx.md`, this file (results, verdict, limitations appended below section 10).

## 10. Deviations (dated; never edits of sections 1-9)

(none yet)

Pilot log (not a deviation): 2026-11-07 18:43 PST, the early single-certificate timing on the development witness
of M02 (sphere_ligaments c 0.40087 w 0.145217, PA12, combined target, as_built off): certified, 1075.3 s
(static 765.5 s, Bloch 309.8 s; `pilot/witness_cert_timing.json`). The 6-method pilot on M02 was still running.

Pilot log 2026-11-07 19:02 PST (development spec M02, not a V3 target; outcomes seen there, protocol unchanged):
6 methods + certificates in 1167 s (search 247 s for all 6 methods, about 50 s per 48-evaluation method; 3
unique certificates 920 s, 284-343 s each, all undetermined; `pilot/driver_children.log`, `pilot/state.json`).
**Pre-run estimate (written before any V3 target was run):**
- 20 primary targets at the pilot's 1167 s = 6.5 h.
- Conservative case of 4 unique certificates per target at about 500 s plus 250 s of search: about 12.5 h.
- 4 calibration targets (2 methods each): about 0.8 h.
- Pilot and smoke test so far: about 0.4 h.
- Total: 7.7-13.7 h, below the 15 h cap, so **no pre-run cut** is applied; the during-run rule of section 7 stays
  in force. The full run had not been started when this was written.

## 11. Results (appended 2026-11-08 02:55 PST, after the full run; sections 1-10 unchanged)

Run: 2026-11-07 19:04 to 2026-11-08 02:45 PST under the GPU lock, `driver.py --spent-hours 0.4`; 20 primary
targets x 6 methods + 4 calibration targets x 2 methods = 128 rows; 85 unique certificates (22,270 s, median
204 s); 8.09 h total including the pilot; no cut applied. Numbers below are from `summary.json` (analyze.py).

| Method | Certified / 20 | 95 % CI | Undetermined | Refuted | Search-tier miss | mean C (evals) |
|---|---|---|---|---|---|---|
| M1 atlas-only | 12 | 0.40-0.80 | 5 | 0 | 3 | 19.2 |
| M2 Sobol | 6 | 0.10-0.50 | 4 | 0 | 10 | 43.7 |
| M3 differential evolution | 9 | 0.25-0.65 | 4 | 1 | 6 | 37.55 |
| **M4 BO full (amm)** | **14** | 0.50-0.90 | 3 | 0 | 3 | 27.1 |
| M5 BO without atlas seeding | 9 | 0.25-0.65 | 3 | 0 | 8 | 42.25 |
| M6 BO without error correction | 14 | 0.50-0.90 | 4 | 0 | 2 | 21.4 |

Primary tests (M4 vs baseline, exact McNemar, Holm over 3):
- vs M1: 14 vs 12 (discordant 2/0), p 0.5, p_holm 0.5; cost diff +7.9 evals (M4 costlier; atlas-only spends 0).
- vs M2: 14 vs 6 (10/2), p 0.039, p_holm 0.116; cost diff -16.6, sign-flip p_holm 0.009.
- vs M3: 14 vs 9 (6/1), p 0.125, p_holm 0.25; cost diff -10.45, p_holm 0.114.
Secondary (ablations): vs M5 14 vs 9 (7/2), p_holm 0.36, cost -15.15 (p_holm 0.006); vs M6 14 vs 14 (4/4), p 1.0.

**Verdict against section 6: NO CLEAR ADVANTAGE.** The best baseline is M1 (atlas-only, 12/20). (A) fails: 14 vs 12
with p_holm 0.5. (B) fails: M4's mean C (27.1) is not <= 50 % of M1's (19.2). No baseline is better than M4.

Reading (descriptive, not tested):
- The atlas carries most of the effect: removing seeding (M5) drops 14 to 9, while atlas-only alone reaches 12.
  This is consistent with the section-1 limitation (witnesses are atlas cells and targets derive from them).
- Error correction adds nothing measurable here (M6 = M4 = 14/20).
- Against atlas-free search (Sobol, DE) M4 succeeds more often and with fewer evaluations; only the Sobol cost
  difference survives Holm.
- The single `refuted` certificate (M3) is a design that passed the search tier and failed certification.
Calibration (nu 0.342/0.39, M4 and M6 only): M4 certified 2/4 (G12, S12), M6 certified 2/4 (G14, S12); M04 undetermined for both.
