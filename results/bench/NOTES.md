# Week 5: benchmark of 100 briefs (E3) and pilot of arms B and C (gate G3)

Status (2026-11-06, after the independent audit, section 8):
- benchmark built: 108 briefs at three truth levels: **witnessed** feasible (74: a design certified against the
  stated request, incl. 3 relabelled near-miss briefs and the ambiguous pairs), **proven** infeasible (16: a
  rigorous bound violated) and **unresolved** (18: no certified witness found by the recorded searches, no bound
  violated; N, 5 near-miss briefs and pairs). Unresolved briefs have no physical ground truth;
- pilot run (development data): 20 briefs x 2 arms, Codex gpt-6.1-sol high on the ChatGPT subscription;
- gate G3 **met as the plan defines it** (unsupported releases): arm B released 4 designs the certificate does
  not support, arm C none. **Not shown**: a reduction in refuted (physically wrong) releases; zero refuted
  releases were observed in either arm over these 28 development sessions per arm, which is not a guarantee;
- rescored with the corrected scorer (section 8): decided briefs (witnessed + proven) B 7/20, C 17/20; unresolved
  briefs: both arms abstained without a proof claim on 8/8.

## 1. Benchmark (bench/v1)

| Class | n | Truth | Source |
|---|---|---|---|
| S feasible static | 20 (10 hard) | release | witness design certified against the stated request |
| G feasible gap | 15 (5 hard) | release | same |
| M feasible combined (stiffness + gap) | 15 (5 hard) | release | same |
| X infeasible, proven | 15 | refuse, PROVEN_INFEASIBLE | a rigorous bound of `amm.bounds` is violated: Voigt E/G/K (10), complete gap through 0 Hz (2), cubic stability nu100 >= 1/2 (2), contradiction (1) |
| N infeasible, not found | 10 | refuse, NOT_FOUND_IN_FAMILIES | atlas oracle NOT_FOUND even for targets relaxed by 10 %, no bound violated (not a proof) |
| R near miss (added after the pilot) | 8: 5 infeasible, 3 relabelled feasible | refuse, or release for the 3 | nominal search value clears the target, certificates refute every checked candidate; 3 labels corrected after arm C certified off-grid designs (section 6) |
| A ambiguous | 25 | ask, then the paired brief's decision | the spec of another brief with one item removed or vague: material 9, cell size 6, which modulus 3, unit 2, complete vs. directional gap 5 (corrected 2026-11-06; first given as 8 / 5); A06/A11 pair with infeasible briefs |

How a feasible truth is made (`scripts/bench/build.py`):
- **Witness.** An atlas cell is chosen. Hard briefs use the family frontier at a random density cap; easy ones
  a random cell.
- **Pass 1.** Certifies targets derived from the search tier: min targets at 0.80 x the median-corrected value,
  the middle half of the corrected gap. Every value is rounded to what the text will say (3 significant figures,
  in the conservative direction) *before* the certificate runs.
- **Easy briefs** keep the pass-1 targets.
- **Hard briefs** take their targets from pass 1's certified bounds and are certified again in pass 2:
  - min targets at 0.97–0.995 x the guarded lower bound;
  - density cap at the guarded upper bound;
  - gap = safe interval less 3 % of its width per side.
- **Bookkeeping.** A witness that does not certify is replaced by the next candidate. Every attempt is kept
  (`bench/v1/work/<id>.json`); full certificates are in `work/certs/`. Six witnesses (G01, G03, M02, S01, S02,
  S03, certified before the certificate cache existed) had no full record; they were re-certified with the current
  checker on 2026-11-06 (`bench/v1/witness_recert.json`, audit F10).

Other details:
- Brief texts are templated with varied phrasing, units (GPa, MPa, kHz, mm, cm) and materials (316L, Ti-6Al-4V,
  PA12, the three atlas Poisson ratios).
- Every brief carries a canary GUID.
- The oracle (scripted user) answers `ask_clarification` from the intended spec (`amm.bench.Oracle`).

## 2. Pilot design

- 20 briefs: S01–S03, G01–G03, M01–M02, X01, X03, X07, N01–N03, A01–A06. A01–A06 pair with pilot briefs, or with
  X01 for A06.
- Arm B: tools without bounds or certificates. Arm C: full system.
- Same prompt for both arms (`amm.bench.PROMPT`).
- One session at a time, with no other GPU or CPU work running. All 40 sessions ran on code `5248c1ad`.
- All 40 recorded `Logged in using ChatGPT` and `forced_login_method=chatgpt` (`codex/auth.txt`).

**Release check.** Every release is certified against the *intended* request: the brief's own spec, normalized
with the intended material and cell size, not what the agent typed (`scripts/bench/scoring.py`). An in-session
certificate counts only if the session's normalized targets and material equal the intended ones. Otherwise the
design is certified afresh (`results/bench/posthoc/`).

**Outcomes:**
- success: release, certified;
- silent failure: release, certificate "refuted";
- unverified release: release, certificate "undetermined";
- false refusal;
- correct refusal, with the verdict compared to the truth;
- no answer.

## 3. Results

| Brief | Class | Difficulty | Expected | Arm B | Arm C |
|---|---|---|---|---|---|
| S01 | feasible static | hard | release | unverified release (undetermined, post hoc) | success (session certificate) |
| S02 | feasible static | hard | release | success (certified post hoc) | success (session certificate) |
| S03 | feasible static | easy | release | success (certified post hoc) | success (session certificate) |
| G01 | feasible gap | hard | release | false refusal (UNDETERMINED) | success (session certificate) |
| G02 | feasible gap | easy | release | unverified release (undetermined, post hoc) | success (session certificate) |
| G03 | feasible gap | easy | release | false refusal (UNDETERMINED) | success (session certificate) |
| M01 | feasible combined | hard | release | false refusal (UNDETERMINED) | false refusal (UNDETERMINED) |
| M02 | feasible combined | easy | release | false refusal (UNDETERMINED) | false refusal (UNDETERMINED) |
| X01 | infeasible proven | – | refuse | correct refusal (PROVEN_INFEASIBLE) | correct refusal (PROVEN_INFEASIBLE) |
| X03 | infeasible proven | – | refuse | correct refusal (PROVEN_INFEASIBLE) | correct refusal (PROVEN_INFEASIBLE) |
| X07 | infeasible proven | – | refuse | correct refusal (NOT_FOUND: weaker verdict) | correct refusal (PROVEN_INFEASIBLE) |
| N01 | infeasible not found | – | refuse | correct refusal (NOT_FOUND) | correct refusal (NOT_FOUND) |
| N02 | infeasible not found | – | refuse | correct refusal (NOT_FOUND) | correct refusal (NOT_FOUND) |
| N03 | infeasible not found | – | refuse | correct refusal (NOT_FOUND) | correct refusal (NOT_FOUND) |
| A01 | ambiguous material | easy | ask, release | success (certified post hoc) | success (session certificate) |
| A02 | ambiguous material | easy | ask, release | unverified release (undetermined, post hoc) | success (session certificate) |
| A03 | ambiguous cell size | easy | ask, release | false refusal (UNDETERMINED) | success (session certificate) |
| A04 | ambiguous quantity | hard | ask, release | no answer (need_info) | no answer (need_info); **success after the oracle fix** (section 4) |
| A05 | ambiguous gap type | easy | ask, release | unverified release (undetermined, post hoc) | success (session certificate) |
| A06 | ambiguous material | – | ask, refuse | correct refusal (PROVEN_INFEASIBLE) | correct refusal (PROVEN_INFEASIBLE) |

| Metric (pilot, code 5248c1ad) | Arm B | Arm C |
|---|---|---|
| Correct decisions | 10 / 20 | 17 / 20 |
| Releases | 7 | 10 |
| Releases the certificate supports (certified) | 3 | 10 |
| Unverified releases (undetermined) | 4 (S01, G02, A02, A05) | 0 |
| Silent failures (refuted) | 0 | 0 |
| False refusals of feasible briefs | 5 (G01, G03, M01, M02, A03) | 2 (M01, M02) |
| Correct refusals of infeasible briefs | 7 of 7 (1 with the weaker verdict) | 7 of 7, all exact |
| No answer | 1 (A04) | 1 (A04) |
| Asked on ambiguous briefs | 6 / 6 | 6 / 6 |
| Asked on clear briefs | 3 (G02, X03, X07) | 1 (X03) |
| Certify calls | – | 16 |
| Session wall time, total | 46.5 min | 131.9 min |
| Input tokens (output) | 9.48 M (31 k) | 17.24 M (40 k) |

Per-session records: `pilot/scores.json`; totals: `pilot/summary.json`.

## 4. Infrastructure and oracle issues found and fixed

1. **Round 0 (`pilot_r0_contention/`, not counted).** The 6 infeasible pilot briefs ran while two
   ground-truth workers shared the GPU.
   - A wide-gap search took 953 s.
   - In arm C on N02, the agent waited "several minutes", then called `evaluate` and `submit`. Both queued
     behind the search on the session lock, and Codex ended the turn with the submit unacknowledged.
   - N03 ended without an answer in both arms.
   - Fixes: no other work runs during sessions; sessions run one at a time; `search` and `certify` state their
     duration in the tool description ("wait for the result").
   - The other round-0 sessions match the pilot (X01, X03, X07, N01 and B N02 all correct refusals).
2. **Ground-truth worker crash.** A safe interval with an unguarded edge (`None`) was compared to a number.
   Such a witness is now skipped, and certificates are cached on disk, so a restart repeats no solve.
3. **Scorer.** A submitted design carries kind and params but not the family; the post-hoc certificate rebuilds
   the spec (`atlas.make_spec`).
4. **Oracle, brief A04** ("a stiffness of at least 6.51 GPa": which modulus?). Both arms asked correctly and got
   "shear modulus". Both then asked for a cell size, which a static brief does not fix. The oracle restated the
   modulus fact, and both stopped with need_info. Fixed in three steps (`amm/bench.Oracle`, `pilot_a04_fix/`):

   | Step | Fix | Result |
   |---|---|---|
   | v1 | Answer "the cell size is not fixed" to a cell-size question | C released a certified Schwarz P sheet (success). B asked with label-only options, which v1 did not catch. |
   | v2 | Also match the question text | B got the answer, then asked whether to accept an unverified design and got the modulus fact again |
   | v3 | After the missing item is settled, answer neutrally ("use your judgement") | B asked for a minimum printable feature thickness, then stopped with need_info, citing printability |

   I stopped there. The remaining stop is arm B holding back from an unverified release. The final wording also
   covers feature thickness; it was not re-run. The table in section 3 keeps the pilot result (no answer in both
   arms); the A04 reruns are on code `692363aa`.
5. **Code hash.** It now covers only the modules that determine tool results. It excludes the oracle (replay
   takes answers from the log), the CLI runner and the MCP transport, so an oracle fix does not mark logs as
   written by other code.
6. **Subscription only, hardened.**
   - Codex runs with `forced_login_method="chatgpt"` (Codex validates the value).
   - API-key and API-endpoint variables are removed from the session environment.
   - The login status is recorded per session.
   - Tests: `tests/test_policy.py`.

## 5. Gate G3

The plan: "B shows silent failures that C removes", with silent failure = "reported success that the certificate
rejects".
- **Met in that sense.**
  - 4 of B's 7 releases are designs the certificate does not support: verdict undetermined against the intended
    request. B's own notes call them "preliminary" or "uncertified" (S01), but they were submitted as releases.
  - All 10 of C's releases are certified.
- **Not shown: a provably wrong release.** No release in either arm was refuted. The closest is B's S01, where
  E100's extrapolated value (0.16056 E_s) lies 0.04 % below the target (0.16062) and the guard band spans
  0.1577–0.1634. It is most likely a miss, but not provably one. B's three gap releases have an edge the
  certificate could not bound.
- **Why.** The pilot has no brief where the search tier says "feasible" but the truth is "infeasible". The hard
  feasible targets sit inside certified bounds, and the N briefs are at least 10 % beyond reach, where both arms
  refuse. A provably wrong release needs a near-miss brief: targets a few % above what the best family designs
  certify, but still met by the biased search tier.

Behaviour worth noting:
- **B is cautious, not reckless.** Without certificates it refused 5 feasible briefs as "UNDETERMINED", mostly
  gap and combined ones. Its search-tier gap screens (objective "pess") found nothing safe enough.
- **C's errors are false refusals on combined briefs** (M01, M02): two undetermined certificates on near-witness
  designs, then a refusal.
- **Infeasible briefs are easy for both arms.** B derived the Voigt bound itself on X01 and refused within 30 s.
  The value of `check_bounds` shows in the verdict (B said NOT_FOUND on X07, a proven case), not the decision.

## 6. Near-miss briefs (class R, added 2026-11-05/06 after the pilot) and the strict reading of G3

**Goal.** Requests the search tier says are met but no design meets, so that a release without a certificate is
provably wrong (`scripts/bench/nearmiss.py`).

**Construction, as it ended up.** Each scenario is a material, a stiffness (E100, G or bulk) and a density cap
on a TPMS grid point.
- The 3 best atlas cells by nominal search value are certified at the certificate's top rung (64, 80, 96, 5 grid
  phases).
- The target goes between the largest certified upper bound and the best nominal value.
- Every atlas cell whose nominal value reaches the target, and the top 3 designs of a nominal-objective search,
  must be refuted.

Two earlier versions found no window at all:
- **Corrected values.** A window between the certified bound and the median-corrected search value (2 scenarios):
  the corrected value is within the 2–4 % guard band of the limit.
- **First rung.** Refutation at the first rung (1 scenario): its bounds sit at the search value.

| | Count |
|---|---|
| Scenarios tried with the final construction | 21 |
| No window | 12 |
| Rounding left the window | 1 |
| Briefs built | 8 (target 10) |

- Bulk modulus never gave a window, and shear modulus once in 6 tries; Young's modulus gave 6 of the 8.
- The windows are narrow: nominal slack +0.2 to +0.9 %, median-corrected slack −2.8 to −10 %.
- Cost: 72 top-rung certificates, 11.9 h of solver time.
- The builder stopped at 8. A single-pass loop skipped scenarios it had deferred for spread; fixed. After the
  results below, I chose not to build 2 more with a construction now known to miss feasible designs.

| Brief | Request | Arm B | Arm C |
|---|---|---|---|
| R01 | Ti-6Al-4V, solid ≤ 16 %, E100 ≥ 8.13 GPa | refuse (NOT_FOUND) | **release, certified** |
| R02 | 316L, ≤ 16 %, G | refuse (UNDETERMINED) | refuse (UNDETERMINED; certificate refuted its candidate) |
| R03 | 316L, ≤ 32 %, E100 | refuse (NOT_FOUND) | refuse (UNDETERMINED; 2 candidates refuted) |
| R04 | PA12, ≤ 24 %, bulk | refuse (UNDETERMINED) | refuse (NOT_FOUND; candidate refuted) |
| R05 | PA12, ≤ 20 %, E100 | refuse (NOT_FOUND) | refuse (UNDETERMINED) |
| R06 | PA12, ≤ 16 %, E100 | refuse (NOT_FOUND) | **release, certified** |
| R07 | 316L, ≤ 24 %, E100 | refuse (NOT_FOUND) | refuse (UNDETERMINED) |
| R08 | Ti-6Al-4V, ≤ 20 %, E100 | refuse (UNDETERMINED) | **release, certified** |

**Three labels were wrong.**
- On R01, R06 and R08, arm C released sphere-ligament resonators between atlas grid points (e.g. c 0.234,
  w 0.2792). Each certified in the session and again in an independent certificate
  (`nearmiss_relabel_check.log`).
- The construction checked grid cells and one 48-evaluation search only. These three are now labelled feasible
  (`work/R0x.json` keeps the original label and the correction).
- After the correction: arm B has 5 correct refusals and 3 false refusals; arm C has 5 correct refusals and 3
  certified releases.
- The other 5 labels are not proofs either. Arm C's certificates refuted or could not certify its candidates
  there.

**Strict G3.** Arm B released nothing on any near-miss brief: 0 of 8.
- It searched with objective "pess" first and "expected" second in every session, never "nominal".
- The values in the tool output are labelled search-tier and biased. B did not treat them as a basis for release.
- With this tool contract, the no-certificate arm does not release provably wrong designs. Its failures are:
  - releases inside the guard band (pilot: 4 of 7, unprovable either way);
  - false refusals (pilot 5, near-miss 3).

**Combined (pilot + near-miss, 28 briefs per arm, corrected labels):**

| Metric | Arm B | Arm C |
|---|---|---|
| Correct decisions | 15 / 28 | 25 / 28 |
| Releases the certificate supports | 3 of 7 | 13 of 13 |
| Releases refuted | 0 | 0 |
| False refusals | 8 | 2 |

Near-miss session cost:
- arm B: 28.3 min, 4.47 M input / 15 k output tokens;
- arm C: 113.3 min, 12.79 M / 32 k, 14 certify calls.
- All 16 sessions ran one at a time on code `692363aa`, with nothing else running.

The paper's claim follows from this. Certificates do not mainly catch reckless releases, which this agent avoids
on its own. They turn the agent's caution into decisions:
- **Releases.** C releases 13 certified designs where B releases 3, plus 4 it cannot support.
- **Refusals.** C refuses with evidence: a violated bound proves infeasibility; a refuted candidate only
  supports withholding that candidate, not infeasibility of the request (reworded 2026-11-06, audit F01).
- **Labels.** C found feasible designs that the benchmark's own grid-based labels had missed. The relabelling
  certificates were reruns of the same checker, not an independent method (audit).

## 7. Cost

- Ground truth for the 8 pilot feasible briefs:
  - static: 44–263 s each, uncontended;
  - gap and combined: 757–2400 s each, partly while sharing the GPU.
- Pilot sessions: 178 min of session wall time in total; 26.7 M input tokens (mostly cached) and 71 k output
  tokens, all on the ChatGPT subscription.
- Post-hoc certificates of B's 7 releases: 49.8 min (6 distinct designs; A02 and G02 are the same design and
  request, cached).

## 8. Independent audit and fixes (2026-11-06)

Codex gpt-6.1-sol (effort high, ChatGPT subscription, read-only sandbox) audited weeks 1-5 before E4
(`scripts/audit/codex_audit.py`, `results/audit/week5_2026-11-06/report.md`; a first attempt could read no files
because `--ignore-user-config` drops the Windows sandbox setting: `results/audit/week5_2026-11-06_noaccess/`).
Verdict: not ready for E4; 3 blockers, 8 major, 1 minor. What was done:

| ID | Finding | Fix |
|---|---|---|
| F01 | N and R labels do not establish infeasibility, yet refusals scored as correct | three truth levels (witnessed / proven / unresolved); unresolved briefs scored for scope (abstention vs overclaim), not correctness |
| F02 | certificates keyed by geometry and targets only: a change of material reused them | key includes material and Poisson ratio; certificate and submission record them; scorer checks both |
| F03 | harness: no D, O, Claude or repeats; parallel default 2; timeouts lost the record; scorer skipped missing logs | `scripts/bench/e4.py` (immutable job manifest, serial, GPU-idle check, isolated workspaces, attempts kept), arms D and O, Claude runner, run.json always written, timeout kills the process tree, every scheduled job scored |
| F04 | ambiguous briefs credited without a question; proof overclaims credited; material read from the last call | `correct` needs a resolving question on ambiguous briefs; overclaim outcome; spec snapshotted at submit (older logs rebuilt by re-running the spec calls, undo included); spec_error_release outcome |
| F05 | a solver failure counted as a refutation | solver failure -> undetermined; only invalid geometry (empty, no load path, floating material) refutes |
| F06 | certificate language exceeds demonstrated guarantees; no independent-code check | independent Q2 solver (section 9); wording: "certified" = numerical acceptance under the stated guard assumptions |
| F07 | C had an extra atlas-recommendation channel; no session budgets | `atlas_suggest` for both arms; budgets 400 designs / 4 certificates per session; B vs C called a bundled intervention |
| F08 | pilot specs reused; no statistical unit or analysis plan | development / confirmatory partition by spec (78 briefs, 61 specs confirmatory); `plan/E4_PREREG.md` |
| F09 | identity and isolation not archived | checker hash in every certificate and post-hoc cache key; plan-time snapshot (source zip, data hashes, packages, CLI versions); de-identified requests outside the repository; dependencies in pyproject |
| F10 | 6 witnesses without full certificate records | re-certified (`bench/v1/witness_recert.json`) |
| F11 | texts promised "3D-printable" cells that nothing checks; cubic scope unstated | one scope statement for every arm (cubic cells, linear elasticity, complete gaps, printability not evaluated); "3D-printable" removed (32 brief texts changed, no truth changed) |
| F12 | factual errors (ambiguity counts, P2 robustness, G1 timing, budget) | corrected in place, each marked |

Checked by the audit with no issue: the reported pilot and near-miss arithmetic, the 44 available witness
certificates, the 15 X bounds (cubic scope for X07/X12), brief texts, hand scores, oracle fairness, canary, ChatGPT
authentication of all 56 sessions, probe replay records.

Also found while fixing: agent sessions never had a working shell. Without the user's Windows sandbox setting Codex
refuses every shell command; 36 of the 56 development sessions tried one and were refused. They reached the project
only through the MCP tools.

**Rescored development runs** (`results/bench/rescore_2026-11-06/` keeps the old scores):

| Development, 28 briefs x arm | B | C |
|---|---|---|
| Decided briefs correct (witnessed + proven, 20) | 7 | 17 |
| Witnessed: certified release with the right spec (16) | 3 | 13 |
| Witnessed: false refusals | 8 | 2 |
| Proven: correct refusals (4) | 4 | 4 (4 exact verdicts; B 3) |
| Unresolved: abstentions without a proof claim (8) | 8 | 8 |
| Unsupported releases | 4 | 0 |
| Refuted releases | 0 | 0 |
| No answer (A04) | 1 | 1 |

The earlier "15 / 28 vs 25 / 28" counted the 8 unresolved refusals as correct; they are now reported apart.

**Re-audit of the fixes** (Codex gpt-6.1-sol, same settings; `results/audit/reaudit_2026-11-06/report.md`): F01,
F02, F05, F07 and F12 confirmed fixed; the independent solver judged consistent (upper-bound argument valid for
exact geometry; the checks are necessary, one-sided ones). Not ready, for these reasons, all fixed before E4:

| # | Re-audit finding | Fix |
|---|---|---|
| 1 | the sign test does not test the declared mean | paired sign-flip permutation test of the mean (primary and secondary) |
| 2 | any matching option, even an unrelated or post-submit question, counted as resolving the ambiguity | an answer counts only if it settles the missing item (`amm.bench.MISSING_KEYS`) and comes before submit; the oracle marks the item settled the same way |
| 3 | legacy post-hoc records and session certificates accepted without checker identity | only the current checker with the intended material and nu counts; legacy records only for the old development runs, labelled `checker = "legacy"` |
| 4 | independent check unfinished | finished before E4 (section 9) |
| 5 | the scope statement called every gap complete, which removed the gap-type ambiguity | scope now says the tools compute complete gaps and that a request may not say which kind it means |
| 6 | GPU check advisory | fail closed; exclusive lock shared by every solver runner of the project |
| 7 | a finished but unmoved workspace was rerun; a truncated log stopped scoring | recovery without rerun, atomic run.json; tolerant log reading with a count of bad lines |
| 8 | phases and frozen identity not enforced | `--phase K`; `run` refuses on any drift of code, checker, full source or brief data; `analyze` refuses before phases 1-2 are complete |
| 9 | cell size not part of the spec; a certified release with a wrong spec counted as a witness | cell size checked; spec_error_release on every truth level |
| 10 | F10 still running; forced recertification used the unversioned cache | finished; `--all` bypasses the cache and stores checker-keyed records |
| 11 | isolation relied on an incidental shell failure; hidden files next to the workspace | Codex feature switches off (shell, browsers, computer use, apps, plugins, multi-agent, memories, hooks, image generation, web search); request files outside the workspaces; boundary check passed for both CLIs (`results/audit/boundary_2026-11-06/`) |
| 12 | arm O could not state the two gap-from-0-Hz requests | rigorous bounds checked on the intended request when the tools reject it |
| 13 | POSIX kill path, unchecked taskkill, Claude loaded project settings | new process group, bounded waits, checked taskkill; `--setting-sources ""` |

Development rescore with the tightened rules: unchanged (every question in the development runs settled its
missing item; no cell-size or checker issue among the counted releases). Releases there are checked with the
earlier, unhashed checker (`checker = "legacy"`); E4 uses only the frozen checker.

No development session used any tool other than the amm MCP tools (1,532 MCP calls, no web, browser or file item
in 60 event logs).

## 9. Independent check of the certificates (audit F06, 2026-11-06)

Two checks written apart from `amm/fem.py`, `amm/homog.py` and `amm/bloch.py`, on cells whose voxelization is exact
(grid-aligned `cube_bars`, coverage 0 or 1 in every voxel at n = 20 and 40), so that a conforming model is a
Rayleigh-Ritz model of the true continuum cell. Each test is one-sided and necessary: a failure would show an
unsound certificate; a pass does not prove soundness. Certificates from the frozen checker `f2e482d81382b400`.

1. **Periodic Q2** (`scripts/verify/indep_fe.py`, `run_indep.py`): own 27-node triquadratic hex, own periodic and
   Bloch handling, numpy, scipy and pypardiso only. Effective stiffness and every band at a fixed k are upper bounds.
   Tests: amm certified lower bound <= Q2 value (E100, G, bulk); Q2 band nb+1 at Gamma, X, M, R >= the upper edge
   of amm's certified safe interval.
2. **scikit-fem 12.0.2** (`scripts/verify/skfem_check.py`, installed with the user's approval): third-party
   element and assembly; kinematic uniform boundary conditions (u = E x on the faces), which give a looser but
   still rigorous upper bound on the periodic stiffness. Its ElementHex2 stiffness and mass eigenvalues equal those
   of the Q2 element to 1e-14; a homogeneous cell returns the exact stiffness (error 6e-15).

Cases: 10 planned cells (`c`, `w` over 0.5-0.8 x 0.1-0.3, Poisson ratios 0.3, 0.342, 0.39), plus 6 added gap cases
(below): 16 cases on 13 distinct geometry and Poisson-ratio combinations (the added cases reuse three geometries).

| Check | Cases | Passed |
|---|---|---|
| amm lower bound <= periodic Q2 (E100, G, bulk; 16 cells x n = 20, 40) | 96 | 96 (all also inside amm's [lower, upper]) |
| amm lower bound <= scikit-fem KUBC (16 cells, n = 20) | 48 | 48 |
| scikit-fem KUBC >= periodic Q2 (same space, consistency) | 48 | 48 |
| Q2 band nb+1 >= amm certified upper edge (5 certified gaps; one also at n = 40) | 6 | 6 |
| Q2 band nb <= amm certified lower edge (consistency, not a bound test) | 6 | 6 |

Smallest gap margins: 0.6026 vs 0.5988 (c0.8 w0.3), 0.5677 vs 0.5531 (c0.5 w0.2, n = 40). Static residuals
<= 9e-14; eigen residuals <= 5e-6. Spectra at n = 40 only where the problem has <= 400k unknowns.

**Gap claims that amm refused.** The first five gap claims were the middle half of the `evaluate` (search tier) gap;
three came out undetermined, and the same claims at nu = 0.3 again undetermined (6 cases). In all 6, the Q2 band
nb+1 lies below the claimed upper edge at a high-symmetry point (for example 0.571 < 0.609 at Gamma), so the claimed
gap above band nb = 6 is absent (the Q2 band is an upper bound of the true band): the refusals were right. The search tier shifts gap edges up
by about 0.07-0.1 in f* on these cells (coarse mesh); it is a screening value, as the tool descriptions state, and
releases rest on certificates. Three further claims were then set to the middle half of the Q2 gap at Gamma, X, M, R
(frozen in `run_indep.Q2_GAP_CLAIMS`; chosen from the Q2 results, so these three test the certified edges, not the
choice of claims); all three certified and pass the check above.

Results: `results/verification/indep/summary.json`, `results/verification/skfem/summary.json`.

**Final pre-launch check** (Codex gpt-6.1-sol, `results/audit/pre_e4_2026-11-06/report.md`): section 9 supported
within its limits (wording above made precise); all 18 smoke scores reproduced from the archived certificates;
own-PID fix correct. Not ready for five harness reasons, all fixed before the manifest was frozen: a finished job
interrupted before the E4 fields were added would be rerun (now recovered); scoring certificates ran outside the
solver lock (now inside); two runners could deadlock or race on a workspace (one runner at a time; arm O in a child
process); the frozen identity left out the atlas, error model and pre-registration (now included); `analyze`
accepted stale, incomplete or one-armed score sets (now refused). Smoke run (development briefs, not E4 data):
18 jobs, Codex and Claude sessions used only the amm MCP tools; the injected crash was archived and rerun; the
injected 60 s timeout was killed with its process tree and scored no_answer (its token usage is not available).
