# V10 reproducibility: protocol and log (2026-11-08)

Plan item V10 of `plan/SOFTWARE_PAPER_PLAN.md` (section 5 table; output table T15). No LLM calls, no Codex, no
Chrome. No edits to `amm/`, `app/`, `web/`, `plan/`, `paper/` or `scripts/paper/`. Scripts: `scripts/verify/v10/`.
Outputs: this folder. GPU work runs only under `python scripts/ops/gpulock_run.py v10 -- <cmd>`.

## 1. Protocol (written 2026-11-08 10:37 PST, before any replay was run)

### 1.1 Identities

- Current code (final release): `amm.tools.code_hash()` = `f1a6d625064a6d18`, `certify.checker_hash()` =
  `c5f8c89871b3bad6`, tool schema `amm-tools/3` (read 2026-11-08 before this protocol, no replay run).
- Frozen E4: every one of the 234 E4 jobs recorded code `90f3823f15cbeff4`, checker `f2e482d81382b400`, data
  `de79a79e98e88731`, schema `amm-tools/1` (`results/bench/e4/scores.json`, `run.json`).
- Environment identity is recorded by `scripts/verify/v10/env_identity.py` (python, packages with versions and
  a hash of the sorted list, torch/CUDA, GPU and driver, MKL CBWR status, data files against `amm/data_manifest.json`)
  and compared with `results/bench/e4/snapshot/environment.txt`.
- A replay is **inside the recorded environment** when it runs on this machine, in the `amm` conda env, with the same
  data files (amm-data/1 hashes verified). The code may differ from the log's code only by the documented,
  versioned changes (schema projection, `amm.tools.replay`).

### 1.2 Replay sets

**Set 1, frozen E4 (`e4_frozen`).** A stratified sample of 15 of the 234 E4 sessions (the task fixes 15; the plan
row says "about 30": deviation D1, compute). Strata: arm (D, B, C) x outcome, where outcome is taken from the frozen
scoring output `results/bench/e4/scores.json` field `decision`: released = "release", refused = "refuse", other =
anything else (need_info, none). 5 sessions per arm. Within an arm: 1 per non-empty stratum, the rest by largest
remainder in proportion to stratum size (ties in the order released, refused, other). Draw:
`random.Random(20261108).sample` over the sorted job names of each stratum; strata visited in the order arm D, B, C
and outcome released, refused, other. **Seed 20261108.** Script `scripts/verify/v10/select_e4.py`, output
`e4_sample.json` / `e4_sample.txt`. The sample is not redrawn for any reason (cost included).
Expected strata sizes (scores.json): B released 15, refused 62, other 1; C released 52, refused 26; D refused 72,
other 6 (D released and C other are empty). Hence allocation B 1/3/1, C 3/2/0, D 0/4/1.

Replay: `amm.tools.replay` with default arguments, i.e. the current code in a `Session(schema="amm-tools/1")`, results
projected to schema 1, checker identity aliased to the logged one (`KNOWN_CHECKERS`). Expected: exact, except where a
later documented change applies. Known candidates, stated now: (a) the B1 refusal-evidence rule for profile-C
refusals without a matching record (static audit `results/software/b1_refusal_audit.json`: only
`codex-C-r1-M13` among E4 jobs); (b) V2-2..V2-4 input checks (NOTES_V2_fixes: no E4 log is affected); (c) anything
else is a finding and is investigated to a cause.

Set 1b (optional, targeted, not part of the sample): `codex-C-r1-M13` (the known B1 decision change; logged tool
time 2,610 s). Run only if the GPU budget allows after sets 1-3 (rule 1.6), and reported apart from the sample.

**Set 2, final-release regression (`release_*`)**, current code only, all expected exact:
- `release_v6`: V6 case sessions under the current code: `case1/session_design`, `case1/session_reference`,
  `case2/session_PA12`, `case2/session_316L`, `case2/session_scaling_316L`, and the V6 GUI sessions
  `case1/gui_sessions/live-20261108-083130-d69b` (empty) and `live-20261108-083132-7040`. The archived first case-1
  sessions (`case1/archive_code_e0350cf7/`, code e0350cf7, superseded) are not in the regression set; V6 NOTES 8.4
  already reports their replay (cited, not redone).
- `release_tutorial`: `examples/outputs/02_session`, `03_session` (code 5970bf55, schema 2: cross-code replays
  through the schema-2 projection and code alias).
- `release_gui`: the B4/B5 live GUI sessions `results/gui/sessions/live-20261108-060336-5e8b`, `-060337-8729`,
  `-060500-1bed` (code 5970bf55, schema 2).
- `release_smoke`: the 5 smoke sessions (codex-C-r1-X01, -N01, -N02, codex-B-r1-S01, codex-C-r1-S01; code 90f3823f,
  schema 1), replayed inside the bit-identity reference run below.
- `release_reference`: `scripts/software/b1b3_reference.py results/verification/v10/b1b3_reference_v10.json`, then
  `--compare results/software/b1b3_reference_final.json results/verification/v10/b1b3_reference_v10.json`; pass =
  132 entries compared, "DIFFERENT: none" (the script excludes timing fields and the certificates' checker field).
- Cited, not redone: V2's 173 replays (`results/verification/v2/replays.csv`).
- Optional (rule 1.6), `probe_old`: `results/probe/C/P1..P5/session` (code b072e26f, older than the E4 code;
  results/gui/NOTES.md expects differences: certificate key without material, submit without spec, get_session
  without budget). Reported apart; not part of the regression verdict.
- Not included: `results/verification/v4/latency_session` (a performance-measurement session; not named by the
  task).

**Set 3, cross-environment (`xenv_linux`).** CPU only, in a throwaway container from the already-pulled
`python:3.12-slim` image (no other image pulled), following B6 3b: `docker run --rm`, `--cpus 8 --memory 16g`, no
GPU; inputs mounted read-only; CPU torch from the PyTorch CPU index, amm installed non-editable from a byte copy of
the current `amm/` source (so the code hash must be `f1a6d625064a6d18` inside), the data mounted and
`AMM_DATA_DIR` set. Sessions (short, no long certify):
1. `examples/outputs/02_session` (evaluate with C*, one small certificate, submit);
2. `examples/outputs/03_session` (screen_manufacturing x2, export);
3. `results/bench/smoke/jobs/codex-C-r1-N02` (schema-1 projection; check_bounds, list_families).
If amm cannot replay CPU-only, that is recorded as the finding; amm is not changed.

### 1.3 Classification of one replay

- **exact**: `amm.tools.replay` reports `exact` (per call: ok flag, state hash, result hash with timing fields
  removed, error text) and no `decision_changes`.
- **within tolerance** (set 3 only): not exact, but in every call: same tool and ok flag, same error text, every
  non-numeric field equal except environment fields (`bloch_device`, path separators), every numeric field within
  the tolerance of 1.4. Hash-like fields (`sha256`, `bytes`, `result_hash`, `state_hash`, `spec_hash`, keys) are
  listed but do not decide, except that a hash difference in a call with no other difference is "unexplained" and
  fails.
- **differing**: anything else; each is investigated and its cause recorded (later fix, environment, amm bug).
- Sets 1 and 2 are inside the recorded environment: the pass criterion is exact; the tolerance numbers are still
  computed (diagnostic only).

### 1.4 Tolerances (set 3), fixed now

- float64 quantities (static homogenization C* and everything derived from it, certificate bounds and verdict
  inputs, bounds, atlas rows, geometry, screening, export numbers): relative difference <= **1e-8**.
- search-tier Bloch quantities (complex64 eigen-solves; GPU on Windows vs CPU in the container; any path through
  keys `gaps`, `gaps_Hz`, `best_rel_gap`, `bands`, and every number of a `search` result): relative difference
  <= **1e-3**.
- relative difference = |a - b| / max(|a|, |b|, 1e-6) (absolute floor for round-off zeros such as the off-diagonal C
  entries ~1e-17).
- Categorical results must be identical: ok flags, verdicts, outcomes, decisions, designs, error text.
- Reason for the numbers: B6 found E100 equal to 15-16 digits between Windows CPU and Linux CPU (float64); search
  tier is complex64 and a different summation order moved low band edges by up to ~5e-4 before the deterministic
  assembly (amm/bloch.py comment), so 1e-3 bounds that effect.

### 1.5 Order of runs and compute

1. env_identity (no GPU). 2. E4 sample selection (no GPU), sample appended to section 2 before any replay.
3. `release_reference` (incl. smoke), `release_tutorial`, `release_gui`, `release_v6` under the lock.
4. `e4_frozen` under the lock (keep_awake on the runner PID).
5. `xenv_linux` in Docker (CPU only, no lock: it does not use the GPU); may overlap step 4.
6. Optional: `probe_old`, then set 1b, if the budget allows.
Estimated GPU time from logged tool seconds: regression about 70 min, E4 sample stated in section 2 after selection.

### 1.6 Budget and stop rules

- GPU budget about 2-3 GPU-hours (lock-held wall time). Optional items only if the lock-held total so far plus their
  logged tool time stays under 3 h.
- A replay that raises is recorded as differing with the exception text; the set continues.
- Only processes started here are stopped, by PID. Deviations are logged in section 5 with dates.

## 2. E4 sample (filled after selection, before replay)

`python scripts/verify/v10/select_e4.py` (2026-11-08 between 10:37 and 10:39 PST, seed 20261108) -> `e4_sample.json`,
`e4_sample.txt`. Strata sizes as expected in 1.2; allocation D 0/4/1, B 1/3/1, C 3/2/0 (released/refused/other).
`codex-C-r1-M13` was not drawn (it stays the optional set 1b).

| job | arm | stratum | decision / verdict | E4 score outcome | calls | certify | search | logged tool s |
|---|---|---|---|---|---|---|---|---|
| codex-D-r1-G15 | D | refused | refuse / UNDETERMINED | false_refusal | 4 | 0 | 0 | 0.0 |
| codex-D-r1-M12 | D | refused | refuse / UNDETERMINED | false_refusal | 4 | 0 | 0 | 0.0 |
| codex-D-r1-M15 | D | refused | refuse / UNDETERMINED | false_refusal | 4 | 0 | 0 | 0.0 |
| codex-D-r1-S14 | D | refused | refuse / UNDETERMINED | false_refusal | 3 | 0 | 0 | 0.0 |
| codex-D-r1-X05 | D | other | need_info / None | no_answer | 3 | 0 | 0 | 0.0 |
| codex-B-r1-S09 | B | released | release / None | success | 10 | 0 | 0 | 5.6 |
| codex-B-r1-A07 | B | refused | refuse / UNDETERMINED | false_refusal | 15 | 0 | 2 | 194.3 |
| codex-B-r1-M14 | B | refused | refuse / UNDETERMINED | false_refusal | 14 | 0 | 1 | 63.9 |
| codex-B-r1-S14 | B | refused | refuse / UNDETERMINED | false_refusal | 11 | 0 | 1 | 107.4 |
| codex-B-r1-N09 | B | other | none / None | no_answer | 16 | 0 | 2 | 282.8 |
| codex-C-r1-A15 | C | released | release / None | success | 23 | 3 | 2 | 1195.6 |
| codex-C-r1-M05 | C | released | release / None | success | 16 | 1 | 1 | 419.2 |
| codex-C-r1-S13 | C | released | release / None | success | 13 | 1 | 1 | 144.3 |
| codex-C-r1-A10 | C | refused | refuse / UNDETERMINED | false_refusal | 25 | 4 | 3 | 1020.5 |
| codex-C-r1-G07 | C | refused | refuse / UNDETERMINED | false_refusal | 15 | 2 | 2 | 677.4 |

Sum of logged tool time 4,111 s (69 min): the projected GPU time of set 1. Profile-C refusals in the sample
(C-A10, C-G07) are candidates for the B1 rule; the static audit accepted both (only M13 rejected).

Environment identity (`env_identity.py` -> `env_windows.json`, before any replay): python 3.10.18, torch
2.5.1+cu124, RTX 4090, driver 610.88 (E4 snapshot: KMD 610.88), MKL CBWR 65538, data files verified against the
manifest. Package list against the E4 snapshot: same versions for every package in the snapshot; the only
differences are pip, setuptools, wheel (absent from the snapshot's freeze) and the way amm and packaging are listed
(editable / local build). So sets 1 and 2 run inside the recorded environment in the sense of 1.1.

## 3. Results

All numbers below are from `replays.csv` / `replays.json` (built by `scripts/verify/v10/build_tables.py` from
`raw/<set>/*.json`), `T15_v10.csv`, `logs/*.log` and `b1b3_reference_v10.json`. Replay code everywhere
`f1a6d625064a6d18`, checker `c5f8c89871b3bad6`, data amm-data/1 verified.

| set | source code (log) | sessions | calls compared | exact | within tolerance | differing | replay s |
|---|---|---|---|---|---|---|---|
| 1 `e4_frozen` | 90f3823f (amm-tools/1) | 15 | 176 | **15** | - | 0 | 3,886.9 |
| 2 `release_v6` | f1a6d625 (amm-tools/3) | 7 | 83 | **7** | - | 0 | 2,839.3 |
| 2 `release_tutorial` | 5970bf55 (amm-tools/2) | 2 | 20 | **2** | - | 0 | 41.6 |
| 2 `release_gui` (B4/B5) | 5970bf55 (amm-tools/2) | 3 | 19 | **3** | - | 0 | 51.1 |
| 2 `release_smoke` | 90f3823f (amm-tools/1) | 5 | 54 | **5** | - | 0 | 386.1 |
| 2 `release_reference` | b1b3_reference_final.json | 132 entries | - | **132** | - | 0 ("DIFFERENT: none") | about 477 wall (incl. smoke) |
| 2 cited: V2 (not rerun) | f1a6d625 | 173 | 1,001 | 171 | - | 2 (probe logs before V2-2..V2-4) | 1,158.5 (V2) |
| 2b `probe_old` (optional) | b072e26f (amm-tools/1) | 5 | 58 | 0 | - | 5 (cause below) | 2,107.7 |
| 3 `xenv_linux` | 5970bf55, 90f3823f | 3 | 30 | 1 | **2** | 0 | 43.3 (container) |

### 3.1 Set 1, frozen E4 (15 of 234)

- **15/15 exact**, 176 calls, no decision change. Every arm and stratum: D 5/5 (refused 4, other 1), B 5/5
  (released 1, refused 3, other 1), C 5/5 (released 3, refused 2).
- All 15 ran through the schema-1 projection with code aliasing (`same_code` false, `code_aliased` true) and the
  checker alias f2e482d81382b400 -> c5f8c89871b3bad6 (source: a recorded certificate for C-A15, C-M05, C-S13;
  `KNOWN_CHECKERS` for the rest). The 11 certificates in the C sessions (A10 4, A15 3, G07 2, M05 1, S13 1)
  reproduce bit for bit under the current checker, as do the 21 search calls of the sample (failed calls included).
- The two profile-C refusals in the sample (C-A10, C-G07, UNDETERMINED with undetermined certificates) are accepted
  by the B1 refusal-evidence rule, as the static audit predicted. The known changed decision (`codex-C-r1-M13`) was
  not drawn in the sample; it was subsequently replayed in section 6: 17/18 calls exact, the expected submit
  rejection, zero numeric differences (consistent with the static audit, `results/software/b1_refusal_audit.json`,
  NOTES_B1B3 section 5).
- Replay time 3,887 s against 4,111 s logged tool time (projection in section 2). B-N09: 170 s vs 283 s logged.
- BoTorch prints `NumericalWarning: A not p.d., added jitter of 1.0e-08` during the replayed searches; the results
  are still bit-identical (the jitter is deterministic).

### 3.2 Set 2, final-release regression

- V6: all 7 exact (design 324 s, reference 762 s, PA12 346 s, 316L 768 s, scaling 323 s, GUI 7040 317 s, GUI
  d69b empty). Same code as the logs (`same_code` true, checker from the header, no aliasing). The scaling session,
  not replayed by V6, is exact too. PA12 and 316L took 346 s and 768 s here against 1,041 s and 982 s in V6 (V6
  ran them under contention, V6 NOTES deviation 5).
- Tutorials 02 (certify) and 03 (export into a temporary root) exact; B4/B5 GUI sessions 8729 (certify + export),
  1bed and 5e8b (empty) exact. These are cross-code replays (logs by 5970bf55) through the schema-2 projection.
- Bit-identity reference: `logs/release_reference_compare.txt`: 132 arrays/dicts compared, "DIFFERENT: none";
  5/5 smoke replays exact (X01 0.2 s, N01 71.9 s, N02 1.0 s, B-S01 and C-S01 in `b1b3_reference_v10.json`). The
  checker field differs as designed (f141e46c in the final reference, c5f8c898 now) and is excluded by the script.

### 3.3 Set 2b, older-code probes (optional, run under rule 1.6)

0/5 exact, as expected in 1.2. In all five: ok flags, decisions and errors identical, **0 numeric differences**
(certificates and searches included), no decision change. The mismatches are contract fields added after code
b072e26f: get_session gains budget/budget_used and lists atlas_suggest (14 tools, log 13); the certificate key and
record carry material, nu and checker (so the state hash of certify and the calls after it differ); submit records
the spec. Per-session causes in `causes.json`. Not part of the regression verdict.

### 3.4 Set 3, cross-environment (Linux container, CPU only)

Container: Debian 13, Python 3.12.16, torch 2.15.0+cpu (CUDA false), numpy 2.5.4, scipy 1.18.1, mkl 2026.2.0,
scikit-image 0.26.0 (`linux/pip_freeze.txt`), MKL CBWR 65538, code hash `f1a6d625064a6d18` and checker
`c5f8c89871b3bad6` inside (byte copy of `amm/`), data verified. Installs 30 s + 50 s, replays 45 s, total 129 s
(`linux/run_linux_console.log`). **CPU-only replay works**; no amm change was needed.

- `codex-C-r1-N02` (schema 1; check_bounds, list_families): **exact** off the recorded environment.
- `02_session` (evaluate with C*, a small certificate, submit): not exact, **within tolerance**. 297 numeric
  differences, all float64 round-off: largest relative difference 9.5e-9 at an off-diagonal C_MPa entry of order
  1e-13 (measured against the 1e-6 floor), first difference C[0][0] 6.1e-16 relative, certificate G_MPa 5.8e-15,
  certificate bounds at most 1.1e-14. Verdict, outcome and submit decision identical. No search-tier numbers
  differed (the design has no gap), so the 1e-3 tier was not exercised.
- `03_session` (screening x2, export): not exact, **within tolerance after diagnostic D3**. Screening
  `removed_islands_fraction` 3.49e-16 (log) vs 0.0 (Linux); both STL files bit-identical (same sha256); report.json
  4,973 vs 4,938 bytes, different sha256. The automatic rule flagged the report hash as unexplained (no numeric
  difference in the export result itself). D3 replayed the session in the container into a kept root and diffed the
  report (`linux/diag03_console.log`, `linux/diag03_report_linux.json`): the only changed lines are the two
  `removed_islands_fraction` values and four export volumes (`volume`, `volume_rel_diff` of cell and tiled block),
  all float64 round-off (volumes 1.2e-16 to 5.6e-15 relative; the fraction 3.5e-16 absolute). All within the 1e-8 tier.

### 3.5 Compute

- GPU (lock-held wall time, Windows): queue_release 10:39:04-12:40:56 (121.9 min: reference + smoke, tutorials,
  GUI, V6, E4), probe_old 12:41:02-13:16:13 (35.2 min), one test replay of codex-D-r1-S14 (0.2 s). **Total about
  157 min (2.6 h)** of lock-held time; the solver is partly CPU (PARDISO), so actual GPU busy time is lower.
  *Updated by the section 6 addendum:* the targeted M13 replay added 1,790.8 s (29.8 min), for about 187 min (3.1 h)
  overall. This exceeds the 3 h cap of rule 1.6; the lead ran it deliberately after the main run to document the
  known decision change.
- CPU only: Linux container 129 s, plus diagnostic D3 (one more container with the same installs and one replay; not timed).
- No LLM calls.

## 4. Findings

1. **No amm bug found.** Every replay inside the recorded environment is exact: 15/15 frozen-E4 (176 calls, 11
   certificates), 17/17 final-release sessions (176 calls), 132/132 reference entries.
2. **Frozen E4 replays on the final code**: schema-1 projection plus code and checker aliasing reproduce results,
   state hashes and decisions bit for bit, certificates included. In this sample no later fix changed anything;
   the only known E4 decision change (C-M13, B1 refusal rule) is outside the sample. *Superseded by section 6:* it
   was replayed afterwards as set 1b (17/18 calls exact; only the expected submit rejection; 0 numeric differences).
3. **Exactness is environment-bound, as amm documents** (B3 CPU fallback "not bit-identical"): on Linux CPU, float64
   results move at 1e-16 to 1e-14 relative. Decisions are unaffected. One practical consequence: the export
   report.json embeds float64 numbers (screening fraction, volumes), so its sha256 is not portable across
   environments while the STL files are; a cross-environment check should compare the report's fields, not its
   hash. Reported, not changed.
4. The cross-environment check did not exercise the search-tier (complex64 Bloch) tolerance: neither chosen session
   has a gap band or a search. A gap-design session without a long certificate would be needed.
5. The plan's "about 30" E4 sessions were cut to 15 (task); the sample covers every non-empty arm x outcome stratum.

## 5. Deviations

- D1 (2026-11-08, before any run): sample size 15, not the plan's "about 30" (task instruction; compute).
- D2 (2026-11-08, before the Linux run): `v10lib.py` computed its default ROOT eagerly
  (`Path(__file__).parents[3]`), which fails inside the container; changed to a lazy default before the container
  ran. The Windows queue had already started; its processes import the module per set and both versions give the
  same paths on Windows.
- D3 (2026-11-08, right after the Linux run, before any E4 replay): one extra container run (`scripts/verify/v10/run_diag.sh`, `diag03.py`) to explain the
  report.json hash difference of `03_session`, which the automatic rule of 1.3 had marked unexplained. With the
  diagnostic the classification is "within tolerance" (`causes.json` records the override and its reason). The
  Linux run itself overlapped the GPU queue (allowed by 1.5).
- D4 (2026-11-08 13:16; *closed by section 6, which replayed it at 13:19-13:49*): set 1b (`codex-C-r1-M13`, 2,610 s logged) not run: lock-held total after probe_old was
  about 157 min, and 157 + 44 min exceeds the 3 h cap of rule 1.6.
- Not a deviation, noted: release_smoke rows come from the reference run (`b1b3_reference_v10.json`), not from
  `replay_set.py`, so they carry no tolerance numbers.

## 6. Files

- Protocol and log: `NOTES.md` (this file). Tables: `replays.csv`, `replays.json`, `T15_v10.csv`; `causes.json`.
- Sample: `e4_sample.json`, `e4_sample.txt`; lists `lists/*.txt`. Environment: `env_windows.json`,
  `linux/pip_freeze.txt`.
- Raw per-session results: `raw/{e4_frozen,release_v6,release_tutorial,release_gui,probe_old,xenv_linux}/*.json`.
- Reference: `b1b3_reference_v10.json`, `logs/release_reference.log`, `logs/release_reference_compare.txt`.
- Logs: `logs/queue_release.log`, `logs/queue_optional.log`, `logs/<set>.log`; Linux: `linux/run_linux_console.log`,
  `linux/replays_linux.log`, `linux/diag03_console.log`, `linux/diag03_report_linux.json`.
- Scripts (`scripts/verify/v10/`): `v10lib.py`, `replay_set.py`, `select_e4.py`, `env_identity.py`,
  `build_tables.py`, `queue_release.sh`, `queue_optional.sh`, `run_linux.sh`, `run_diag.sh`, `diag03.py`.
- Workspace (throwaway, outside the repo): `C:\AI\AgenticMetamaterials_workspaces\v10\` (container inputs and
  outputs). Containers `amm_v10_linux` and `amm_v10_diag` were removed by `--rm`.

## 6. Addendum (lead, 2026-11-08 13:19-13:49): targeted replay of codex-C-r1-M13 (closes deviation D4)

The known B1 decision change was replayed after the main run, under the lock (set `e4_targeted`, `lists/e4_targeted.txt`, log `logs/e4_m13_extra.log`; raw file moved from `raw/e4_m13_extra/` to `raw/e4_targeted/` with its `set` field renamed). Result: 18 calls compared, 17 exact. The only difference is seq 18 `submit`: the logged UNDETERMINED refusal (ok) is now rejected by the B1 refusal-evidence rule, because the session holds only search_not_found (seq 15) and certificate_refuted (seq 16) records, not an undetermined certificate. 0 numeric differences. This matches the B1 static refusal audit (results/software/NOTES_B1B3.md). Replay time 1,791 s (logged tool time 2,610 s). T15 now carries row "1b frozen E4 (targeted)", classified differing with this cause.
