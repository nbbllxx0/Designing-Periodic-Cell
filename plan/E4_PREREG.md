# E4 pre-registration (frozen before the first confirmatory session)

Written 2026-11-06 after the independent audit (`results/audit/week5_2026-11-06/report.md`). The job manifest
`results/bench/e4/jobs.json` (with `meta.code`, `meta.checker` and `snapshot/`: source zip, data hashes, packages and
CLI versions) is written once by `scripts/bench/e4.py plan` and never changed. Any later change to code, prompts,
budgets or scoring is logged in section 9 with its date; it does not silently re-run finished jobs.

## 1. Units and partition
- Statistical unit: the **intended specification** (`scoring.spec_key`); 108 briefs = 83 specifications (25
  ambiguous briefs share their pair's spec). Repeats and presentations of one spec are averaged before any test.
- **Development** partition: specs seen in the pilot or near-miss runs, incl. ambiguous pairs: 30 briefs, 22 specs.
  Oracle fixes, the near-miss construction and the R relabelling used these outcomes, so they are reported apart.
- **Confirmatory** partition: the other 78 briefs, 61 specs (58 witnessed, 12 proven, 8 unresolved briefs).

## 2. Arms (same brief text, oracle, scope statement and budgets)
- **D**: the LLM alone. No tools; JSON answer; up to 2 clarification questions answered by the same oracle
  (`amm.bench.DIRECT_PROMPT`). The harness logs the answer through the tool contract.
- **B**: spec tools, `ask_clarification`, `list_families`, `atlas_suggest`, `evaluate`, `search`, `submit`.
- **C**: B plus `check_bounds` (rigorous bounds and the atlas feasibility verdict) and `certify`; a release needs a
  certificate for the design, targets and material. B vs C is a **bundled** intervention (bounds + atlas verdict +
  certificates), not certificates alone.
- **O**: no LLM; oracle spec; bounds, atlas cells, a 48-evaluation search, up to 3 certificates
  (`amm.bench._run_baseline`). A search reference, not a language-understanding arm; non-ambiguous briefs only.
- Session budgets, equal for B and C: 400 designs evaluated, 4 certificates (C), 90 min wall time. Never reached in
  the 56 development sessions (max 288 designs, 3 certificates).

## 3. Back ends and repeats
- Codex CLI, gpt-6.1-sol, effort high, ChatGPT subscription (forced login, API-key and endpoint variables stripped;
  checked before every session): D, B, C x 108 briefs x **3 repeats**.
- Claude Code (claude-opus-5-5, claude.ai subscription, no built-in tools): D, B, C x 108 x 1 repeat, exploratory.
- No pay-as-you-go API anywhere.

## 4. Run protocol
- Order: repeat blocks; briefs shuffled inside a block, arm order shuffled per brief (seed 20261107). Jobs run in
  manifest order inside each phase.
- Phases, enforced by `e4.py run --phase K` (`e4.PHASES`): 1 Codex repeat 1 confirmatory; 2 Codex repeats 2-3
  confirmatory; 3 arm O; 4 Codex development, repeats 1-3; 5 Claude. A phase may be cut for cost; the cut is logged.
  The primary analysis needs phases 1-2 complete (`analyze` refuses otherwise, except a labelled `--interim`).
- `run` refuses to start if the tool code, checker, full source (amm/, scripts/bench/), brief data, atlas and error
  model, or this file differ from the plan-time identity in jobs.json (any later edit here needs a logged override).
- One runner at a time; one job at a time under the solver lock that scoring certificates and the verification
  runners also take; a job starts only when nvidia-smi lists no Python compute process (fail closed: an unreadable
  GPU state stops the run). Arm O runs in a child process. During E4 no other solver script is run on this machine.
- Isolation: opaque workspace outside the repository with a de-identified request (text, intended spec, oracle
  facts; no id, class or truth) kept outside every agent workspace. Codex runs with the shell tool, browsers,
  computer use, apps, plugins, multi-agent, memories, hooks, image generation and web search switched off and a
  read-only sandbox; Claude runs with no built-in tools and no settings files. Boundary check of both runners:
  `results/audit/boundary_2026-11-06/` (neither could read a file inside or outside its workspace).
- A crash (no run.json) is moved to `attempts/` and rerun; a finished workspace interrupted before the move is
  recovered; a timeout or error is final and scored as it is (token usage of a timed-out Codex session is not
  available and is reported as missing). No job is rerun for its outcome.
- `analyze` refuses unless every primary job is finished and scored with the frozen checker, no run record is
  newer than the scores, and every compared spec is scored in both arms.

## 5. Scoring (`scripts/bench/scoring.py`, frozen)
- Truth levels: witnessed / proven / unresolved. Every release is certified against the intended request with the
  current checker (session certificate only if targets and material match).
- `correct` (witnessed and proven briefs): success (certified, right material, targets and cell size) or correct
  refusal (proven briefs), and on ambiguous briefs a question before submit whose answer settled the missing item
  (`amm.bench.MISSING_KEYS`). `appropriate` (unresolved briefs): abstention without a proof claim, or a certified
  witness with the right spec.
- Certificates count only from the frozen checker with the intended material and Poisson ratio; anything else is
  certified afresh.
- Reported separately: refuted releases, unverified releases, spec-error releases, false refusals, overclaims,
  verdict match, no answer, questions, designs evaluated, certificates, wall time, tokens.

## 6. Primary hypothesis and test
- H1: on the confirmatory partition with Codex, arm C is correct on more decided briefs than arm B.
- Statistic: mean over specs of (C - B) per-spec correct rate (witnessed + proven briefs).
- Test: two-sided paired sign-flip permutation test of the mean spec-level difference (100,000 random sign flips),
  alpha = 0.05; 95 % CI by a cluster bootstrap over specs (10,000 resamples). Development estimate: C 17/20 vs B
  7/20 on decided briefs.

## 7. Secondary (same test, Holm-adjusted, family of 5; `e4.py analyze`)
1. unsupported releases (refuted + unverified), B - C, all briefs;
2. false refusals, B - C, witnessed briefs;
3. overclaims (PROVEN_INFEASIBLE on unresolved briefs), B - C;
4. correct, C - D, decided briefs;
5. ambiguity resolved, C - B, ambiguous briefs.

## 8. Exploratory (no confirmatory claim)
Claude back end; development partition; near-miss briefs (n = 8: even zero failures bound the rate only below
about 31 % at 95 %); arm O; class-wise rates; cost; replay exactness on a sample of sessions.

## 9. Change log
- 2026-11-06: written before any confirmatory session.
- 2026-11-06 (re-audit, still before any confirmatory session): sign test replaced by the permutation test of the
  mean; phases, frozen-identity check, fail-closed GPU lock, recovery of finished workspaces, hidden request files
  outside the workspaces, explicit Codex feature switches; clarification counted only when it settles the missing
  item before submit; cell size part of the spec; current-checker rule for certificates; the scope statement no
  longer declares every requested gap complete (the gap-type ambiguity briefs stay meaningful).
- 2026-11-06 (final pre-launch check, `results/audit/pre_e4_2026-11-06/report.md`, still before any confirmatory
  session): harness smoke run on development briefs (`results/bench/smoke/`); arm O no longer runs inside the runner
  (self-wait on its own CUDA context found by the smoke run); one runner at a time; finished workspaces recovered
  even before the E4 fields are added; scoring certificates under the solver lock; atlas, error model and this file
  in the frozen identity; analysis refuses incomplete, stale or one-armed score sets. Independent certificate check
  finished (`results/bench/NOTES.md` section 9).
- **2026-11-07, amendment A1** (`scripts/bench/e4.py` `AMENDMENTS["A1"]`; record `results/bench/e4/amendments/`).
  - **Status at the amendment:** E4 was paused on 2026-11-06 at 23:18 by the author. 29 of 234 phase-1 jobs had
    completed and 1 was interrupted. **No confirmatory session had been scored, and no outcome had been read**:
    only process status lines and token counts.
  - **Reason:** the paper was re-planned as a software paper (`plan/SOFTWARE_PAPER_PLAN.md`) because of self-overlap
    with the author's other papers and the LLM cost. Both reasons are independent of E4 outcomes.
  - **Cut:** phases 2 (Codex repeats 2-3), 4 (Codex development) and 5 (Claude) are cut. Phases 1 and 3 run to
    completion.
  - **Primary analysis:** the section 6 test on phase 1 only (Codex repeat 1, confirmatory), with specs as units.
    Secondary tests are Holm-adjusted as in section 7. Output: `e4.py analyze --tag e4 --amended A1` →
    `analysis_A1.json`, labelled amended. Repeat-level reliability cannot be estimated and is reported as missing.
  - **Quota rule:** a session that did not end normally (non-zero exit, not done, or no final answer) and whose
    error channel (CLI stderr, error or failed events) matches a provider usage-limit message is an infrastructure
    interruption, not an answer.
    - The attempt is kept in `attempts/` with its logs and costs.
    - The runner stops, and the same manifest job is rerun after the limit resets.
    - The rule is applied to every job, including those finished before A1 (`e4.py quota-check`).
    - Timeouts, malformed answers and all other failures keep the section 4 rule: final, scored as they are.
    - The estimate therefore describes performance while the service is available; interruptions are reported
      separately.
  - **Identity:** runs under A1 use `--amendment A1` instead of `--allow-drift`. It accepts a difference only in
    `scripts/bench/e4.py` and this file, checked file by file against the plan-time source zip. Tool code, checker,
    brief data, atlas, error model, prompts, budgets and scorer must equal the plan-time identity. Every job records
    the harness hash it ran under.
- **2026-11-07, amendment A2** (`scripts/bench/e4.py` `AMENDMENTS["A2"]`).
  - **Status at the amendment:** phase 1 finished at 11:20 (all 234 jobs, status done, none interrupted). **No job
    had been scored and no outcome had been read**; only process status lines were seen.
  - **Reason:** the author capped total compute for the software paper at 40-60 h (CPU/GPU plus model time); the
    arm-O runs (phase 3, about 61 confirmatory briefs of CPU/GPU search) do not fit. Independent of E4 outcomes.
  - **Cut:** phase 3 (arm O, the no-LLM reference). Arm O was a descriptive reference (section 7 `reference_O`),
    never part of a pre-registered test, so the primary and secondary tests are unchanged.
  - **Analysis:** `e4.py analyze --tag e4 --amended A2` → `analysis_A2.json`; `reference_O` is reported empty. Same
    tests, units, Holm adjustment and quota rule as A1.
  - **Identity:** as A1 (only `scripts/bench/e4.py` and this file may differ from the plan-time source zip).
