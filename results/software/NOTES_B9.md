# B9 log: fixes G1-G6 (live GUI work) and B6-1 to B6-3 (2026-11-08)

Issues from `results/gui/NOTES.md` (GUI section "amm issues found") and `results/software/NOTES_B6.md`, fixed in
`amm/`, with the method of `NOTES_B1B3.md`. No LLM calls. No edits to `scripts/bench/`, `results/bench/`,
`results/verification/` or `plan/`. GPU runs only under `python scripts/ops/gpulock_run.py b9 -- <cmd>`.

## 0. Before editing

- Backup: `C:\AI\AgenticMetamaterials_backups\pre_B9_2026-11-08\` (`amm/`, `app/live.py`, `app/backend.py`,
  `tests/*.py`, `docs/*`, `contract_amm-tools-{1,2}.json`).
- Pre-edit identity: `amm.tools.code_hash()` = `5970bf55108f1584`, `certify.checker_hash()` = `f141e46cb67a78db`
  (the same as at the end of B1-B3 and B6; it wrote the GUI and tutorial sessions).
- Reference for the bit-identity check: `results/software/b1b3_reference_final.json` (132 entries, B1-B3 final).

## 1. What changed (amm/)

- **G1 replay of exports** (`tools.replay`): with `root=None`, a log that holds `export` calls is replayed into a
  temporary session directory (removed afterwards; result field `root`); other logs run without a directory, as
  before. Nothing is compared less: the export result carries the sha256 and size of cell.stl, the tiled STL and
  report.json, and those are compared. report.json records the code and checker identity, which changes with any
  amm edit; as for certificates (the B1-B3 checker alias), the replay session writes the LOGGED identity into the
  report (`code_alias`, `checker_alias`, also for the certificate summary inside it), so the report hash still
  compares every number, file hash and decision. The logged checker comes from the session header (new header
  field `checker`, written since B9), else a recorded certificate, else `tools.KNOWN_CHECKERS` for the logged code
  hash (5970bf55108f1584 and dc9d810c7020a7e9 -> f141e46cb67a78db, 90f3823f15cbeff4 -> f2e482d81382b400, from
  NOTES_B1B3/B6), reported as `identity.checker_log_source`. Calls now replay with the logged seq numbers
  (identical for every existing log, numbered 1..n; needed by G4).
- **G2 transactional call** (`Session._call`): snapshot of seq, `_seq_now`, budget, certificates (summary, full,
  seq), evaluated rows, spec, undo stack and submission; on any BaseException before the record is written they
  are restored, the call's evidence is dropped, nothing is logged, and the exception is re-raised. Files a tool had
  already written (certificate JSON, export files) stay; the last cancel point of export is before it writes files.
- **G3 progress / cancel hook**: new `amm/progress.py` (`hooks(progress, cancel)`, `checkpoint`, `Cancelled`, a
  BaseException) in a context variable; `Session.call(name, args, actor, progress=None, cancel=None)`.
  Checkpoints: every static solve and rung of a certificate, the Bloch block, every Bloch k-point of the inertia
  counts, every gap-edge Lanczos solve and screening count, every adversarial-k round, every as-built case, every
  design of `evaluate_batch`, every search batch, three export stages. Default None: a checkpoint returns at once.
  An Exception raised by a progress callback is swallowed (it must never become a fail-closed verdict).
- **G4 lock**: done, not only documented. The read-only tools `CONCURRENT_READ` (get_session, check_bounds,
  atlas_suggest, list_families) no longer wait while a NON-mutating call (a solve) runs. They run on a view of the
  session as it was when that call started (its budget spend and certificate not yet visible; the spec cannot have
  changed, since only mutating calls change it; the running call adds its evidence only when it commits), under a
  short state lock, and their records are written before the running call's record. Executing the log in file
  order therefore reproduces every result, and replay uses the logged seq numbers, so it is exact (tested: reads
  during an export, then exact replay; and in the live GUI e2e test during a certificate). Mutating calls still
  wait. Why it is safe: of the running non-mutating tools only export reads the evidence list, in its card, which
  filters by the certificate's seq (a concurrent check_bounds record cannot match). A cancelled solve that reads
  overlapped leaves its seq number unused (a gap), never a reused number.
- **G5 bands**: `evaluate(bands=False)`; with `bands=True` each design gets `bands` = {f_star (k x band),
  k_over_pi, k_ticks, n_bloch, n_bands, unit, tier, and hz_per_f_star with material and cell size}. Existing fields
  unchanged; the export report's search-tier row never carries the bands. This adds to the contract, so the schema
  was bumped consistently to **amm-tools/3** (`SCHEMA_V2` constant; decorator `arg_since`; per-schema argument
  models; a schema-2 session rejects `bands`; `project` strips it below 3). `contract("amm-tools/1")` and
  `("amm-tools/2")` are byte-identical to the frozen files (cmp, and a test); `scripts/software/write_contract.py`
  (run, not edited) added `results/software/contract_amm-tools-3.json`; `docs/tool_contract.md` regenerated with
  `docs/gen_tool_reference.py`, which had amm-tools/2 hard-coded and now follows SCHEMA_VERSION (`--check`: up to
  date, frozen copy identical).
- **G6**: `bloch.certify_gap` frees the InertiaCounter in a `finally` (per resolution); `_edges_at` too.
- **B6-1**: `tools.ATLAS_DIR` defaults to None; `tools.atlas_dir()` / `atlas_path(nu)` resolve through
  `amm.data.data_dir()` at each call (AMM_DATA_DIR, else results/atlas of the checkout); `atlas.error_model_path()`
  likewise (ERROR_MODEL_PATH kept as the import-time value). The atlas cache is keyed by path; a missing file is
  not cached. Without AMM_DATA_DIR the same files as before are read.
- **B6-2**: missing atlas file: "the search atlas for nu_s = 0.39 not found: <path> does not exist (AMM_DATA_DIR =
  ... / AMM_DATA_DIR is not set, so amm looked in ...) ... set the environment variable AMM_DATA_DIR ...
  (docs/data.md ...)", as the atlas_suggest error and the check_bounds atlas note. A Poisson ratio outside the data
  set keeps the old text (it may be in logs).
- **B6-3**: chosen: a clear error, no uncorrected run (the objective and the calibrated-domain flags need the error
  model; running uncorrected would silently change what "expected" means). search returns "search cannot run: the
  search-tier error model error_model.json not found: ..." before spending budget; check_bounds reports its atlas
  part UNAVAILABLE with that note; atlas_suggest errors likewise. Documented in docs/data.md and limitations.md.
- `amm/mcp_server.py`: tool signatures from the session's schema (one line).

App: `app/live.py` no longer wraps any amm function (install_hooks, the band tap and its own rollback removed): jobs
call `Session.call(progress=, cancel=)`, and `amm.progress.Cancelled` becomes JobCancelled; live evaluate adds
`bands=True` (logged) and the band diagram reads the bands from the call's record; CONCURRENT_READ tools go straight
to the session, spec changes still answer "session busy". `app/backend.py` unchanged.

Tests: new `tests/test_b9.py` (14). Changed: `test_app_live.py` (the wrapper test replaced by a test of the amm hook
through JobCtx; e2e: counts "static solves" instead of "homogenizations", bands in the evaluate result, reads during
the running certificate, seq gap), `test_outcomes.py` (contract schema_version is now amm-tools/3), `conftest.py`
(data paths through amm.data; 2 slow marks). Docs: tool_contract.md (generated), data.md, limitations.md,
gen_tool_reference.py.

## 2. Verification

- **Bit identity** (`scripts/software/b1b3_reference.py`, under gpulock_run b9; output and log
  `C:\AI\AgenticMetamaterials_workspaces\b9\b9_reference_post.{json,log}`, comparison `b9_compare.txt`) against
  `results/software/b1b3_reference_final.json`: **132 of 132 bit-identical, "DIFFERENT: none"**. No field was
  excluded beyond what the script always excludes: `checker` of the two certificates (code identity) and the
  timing fields (seconds, timing, dt_s, batch_seconds_per_cell, static_s, bloch_s, t, edge_extra_seconds). The new
  band output is not on these call paths (tool level only). MKL CBWR 65538.
- **Replays, default arguments**: 5 smoke sessions (inside the reference run) 5/5 exact (C-S01 with the checker
  alias); GUI `live-20261108-060337-8729` (13 calls, certify + export; temporary root; checker from results) exact,
  `live-20261108-060500-1bed` (6 calls) exact, `live-20261108-060336-5e8b` (empty log) exact;
  `examples/outputs/02_session` (12) exact, `03_session` (8, export; temporary root; checker from KNOWN_CHECKERS)
  exact. Script and output: `...\b9\b9_replays.py`, `b9_replays.json`, `b9_replays.log`.
- **Tests**: `python scripts/ops/gpulock_run.py b9 -- python -m pytest -q -rs -p no:cacheprovider`: **165 passed,
  0 skipped, 0 failed** in 311 s (was 151; +14 in test_b9.py; test_app_live.py keeps 3). Log
  `...\b9\b9_full_tests.log`; lock file absent afterwards.
- **Wheel** (`pip wheel . --no-deps` from a clean copy of pyproject.toml, README.md and amm/, PIP_CONFIG_FILE=nul;
  amm-0.2.0-py3-none-any.whl, 105,184 B, sha256 e8a958dba3f0...9c93, contains progress.py; the copy was checked
  equal to amm/ after the tests), installed (core only, 1.7 min) into
  `C:\AI\AgenticMetamaterials_workspaces\b9_venv` (Anaconda base Python 3.11.5), run from outside the checkout with
  `-I`, CPU only. With `AMM_DATA_DIR=C:\AI\AgenticMetamaterials\results\atlas`: amm from site-packages,
  `data.verify()` ok, check_bounds NOT_REFUTED / atlas FEASIBLE (892 of 2714 cells), atlas_suggest sphere_ligaments
  c 0.12, w 0.181739 (as in B6 with the workaround). Without it: atlas UNAVAILABLE with the B6-2 message,
  atlas_suggest the same message, search "needs BoTorch" (core install). The venv and the source copy were deleted.
- **Identities**: code hash 5970bf55108f1584 -> 5ab7480410467482; checker hash f141e46cb67a78db ->
  c5f8c89871b3bad6 (bloch.py and certify.py changed, progress.py joined the closure: 10 files). The frozen E4
  checker (f2e482d81382b400, in the pre-B1B3 backup and the E4 source zip) and results/bench/e4/snapshot are
  untouched; no file under results/bench, scripts/bench, results/verification or plan changed (find -newer).
- GPU time under the lock: reference + smoke replays about 8 min, other replays 1.5 min, test_b9 0.7 min, the full
  suite twice about 11 min: about 21 min in total.

## 3. Incidents and open points

- First full run: 164 passed, 1 failed: `test_evaluate_bands_are_additive` read the gaps of a design that has none
  (a test bug). Fixed by using cube_bars c 0.6, w 0.2 (a known gap former); log `b9_full_tests_run1.log`.
- The verification outputs are in `C:\AI\AgenticMetamaterials_workspaces\b9\` (only NOTES_B9.md was allowed in
  results/software); move them into the repo if they should stay with the paper.
- The bump to amm-tools/3 makes text that calls amm-tools/2 the current schema one version behind (paper,
  docs/concepts.md and other docs pages, the examples/01 docstring, the app/backend.py mock-mirror constant); not
  edited here (outside the allowed edits). The mock GUI mirror stays a schema-2 mirror.
- A nested call from inside a running tool on the same thread (e.g. a progress callback calling session.call) is
  not supported (it was not before either).
