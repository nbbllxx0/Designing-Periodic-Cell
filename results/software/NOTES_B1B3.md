# B1-B3 progress log (2026-11-07)

Plan items B1 (refusal evidence, outcomes, schema versions, full C*), B2 (export, as-built tool, manufacturing
screening) and B3 (isolation and packaging) of `plan/SOFTWARE_PAPER_PLAN.md`. E4 had finished and been scored before
any edit; `results/bench/` is read only.

## 0. Before editing

- Backup of `amm/`, `tests/`, `app/` and `pyproject.toml`: `C:\AI\AgenticMetamaterials_backups\pre_B1B3_2026-11-07\`.
- Pre-edit identities: `amm.tools.code_hash()` = `90f3823f15cbeff4` ; `certify.checker_hash()` = `f2e482d81382b400` (the frozen E4 checker). The code wrote the 18 current-code smoke
  sessions and E4.
- GPU runs (tests, reference outputs) hold the shared solver lock through `scripts/ops/gpulock_run.py` (same
  protocol as `scripts/bench/e4.py` GpuLock).
- Baseline test suite before any edit: **109 passed** in 247 s (`pytest tests`, under the solver lock).

## 1. Static scan of recorded refusals (read only, before editing)

The planned B1 rule (profile C: a refusal must cite a held record of the matching kind) was checked against every
recorded log (smoke, pilot, probe and the finished E4 jobs; read only). Profile-C refusals with no record of the
matching kind at all:
- `results/bench/pilot/C/X03` and `results/bench/e4/jobs/codex-C-r1-X11`: PROVEN_INFEASIBLE for a gap that contains
  f = 0. `set_target` rejected the gap (rule W1), so `check_bounds` had no target to check. The refusal is right
  (W1 is a rigorous bound) but no `check_bounds` record exists. Decision: the W1 rejection by `set_target` is itself
  logged as a bound record (kind `bound_violation`, bound W1), valid while no gap target is set. Without this an
  agent could never refuse such a request.
- `results/bench/e4/jobs/codex-C-r1-M13`: UNDETERMINED, but the session holds a bounded search with nothing found
  (seq 15) and a *refuted* certificate (seq 16), no undetermined certificate. Under B1 this refusal is rejected;
  the rejection message points to NOT_FOUND_IN_FAMILIES (seq 15). This is a changed outcome (E4, not replayed).
- Profile B refusals mostly carry no record (B has neither `check_bounds` nor `certify`). The rule is applied to
  profile C only, as the release rule is; profile B is the E4 ablation arm and keeps its contract.

## 2. Reference outputs before editing (`scripts/software/b1b3_reference.py`)

`results/software/b1b3_reference_pre.json` (log `b1b3_reference_pre.log`), recorded with the pre-edit code under the
solver lock, MKL CBWR status 65538 (AUTO|STRICT):
- geometry: 119 entries (all 9 kinds; `design_cell` at n = 12, 16 and phases 0, 1/8, 1/4, 1/2; an eroded phased
  cell; `design_cells` (10, 20) from n_fine 60; binary and dilated `make`; `field`; `tpms_field`; `grid`), each
  array as sha256 of its bytes with dtype and shape;
- homog: C* of 5 cells at n = 14 (array hash) plus every scalar output;
- bounds: `bounds.check` (feasible and violated request) and `atlas.oracle` over the nu = 0.3 atlas;
- evaluate: 3 cells through `evaluate_batch` at the search tier (GPU bands; full row and band array hashes);
- certify: two small certificates (static and gap claims; ladder (8, 10, 12), Bloch (8, 10), edge 12, phase 0.5,
  adversarial n = 6, as-built on); both end undetermined, the full certificate minus `checker` is hashed;
- replay of 5 smoke sessions (codex-C-r1-X01, -N01, -N02, codex-B-r1-S01, codex-C-r1-S01; 54 calls incl. one
  certificate and three searches): **5/5 exact** on the pre-edit code (same_code true), 380 s.

Incident (2026-11-07, during B1): one ad-hoc replay of a probe session was started without the solver lock; it was
stopped after < 2 min by its task id (it was in a search/certify call). No result was written.

## 3. What changed

### B3 isolation and packaging
- `amm/geometry.py`: the module global `_SHIFT` is gone. `grid(n, shift)`, `tpms_field(kind, n, shift)`,
  `field(..., shift=)`, `_fine_coverage(..., shift=)` take the translation explicitly; `design_cell(phase=)` passes
  `shift = phase / n` down. Same arithmetic (`((i + 0.5) / n + shift) % 1.0`; shift 0.0 adds 0.0), so every call
  path is bit-identical (section 4). Two threads voxelizing at different phases no longer interfere (test).
- `amm/__init__.py` solves nothing. New `amm/_runtime.py`: environment defaults (MKL_NUM_THREADS=16,
  MKL_CBWR=AUTO,STRICT) at import, as before; a `sys.meta_path` guard runs the 1x1 PARDISO warm-up just before the
  first `torch` import (also when botorch or gpytorch import it), and `amm.pardiso.Pardiso` runs it before the
  first solver, so the sequence of MKL calls is the old one. `amm.MKL_CBWR_STATUS` still exists (lazy, module
  `__getattr__`). torch imported before amm: the old code aborted the process at `import amm` (OMP Error #15,
  checked with the backup); now `import amm` succeeds and the first MKL use raises a RuntimeError saying to import
  amm first (AMM_ALLOW_TORCH_FIRST=1 overrides). The ordering guarantee is written out in `amm/_runtime.py`.
- Checker identity: `certify.checker_files()` = certify.py + the transitive closure of its amm imports (AST,
  including imports inside functions) + units.py, `__init__.py`, `_runtime.py`. Now 9 files (was a fixed list of
  7): adds `__init__.py` and `_runtime.py`. A new module imported by the checker joins automatically (test).
  `checker_hash()` recomputes the list at every call.
- Optional extras (`pyproject.toml`, version 0.2.0): core = numpy, scipy, pypardiso, mkl, torch, pydantic;
  extras `search` (botorch, gpytorch), `mcp`, `gui` (starlette, uvicorn), `export` (scikit-image), `gpu` (cupy;
  amm never imports it), `verify`, `all`, `test`. Clear errors: the `search` tool without BoTorch returns
  "amm.search (the `search` tool) needs BoTorch and GPyTorch: pip install amm[search]"; the MCP server without the
  SDK raises "... pip install amm[mcp]". CPU fallback: `bloch.resolve_device("cuda")` gives "cpu" without a CUDA
  device (evaluate rows then carry `bloch_device: "cpu"`; not bit-identical to the GPU). Export falls back to voxel
  faces without scikit-image. The GUI (`app/`) stays in the source tree, outside the wheel.
- Data packaging (`amm/data.py`, `amm/data_manifest.json`, `scripts/software/make_data_manifest.py`): data set
  `amm-data/1` = the three atlas files and `error_model.json` (runtime), `calibration*.json` (provenance),
  `results/atlas/NOTES.md`; per file bytes, sha256 and generator script. `identity.e4_data_hash` =
  de79a79e98e88731, equal to the `data` identity recorded by every E4 job. The wheel ships only the manifest; the
  files go to Zenodo at release (field `zenodo` null until then; licence left to the authors); a user points
  `AMM_DATA_DIR` at the downloaded folder and `amm.data.verify()` checks the hashes. Without AMM_DATA_DIR the same
  files as before are read.

### B1 refusal evidence, outcomes, schema versions, C*
- `amm/outcomes.py` (schema `amm-outcome/1`): outcomes certified_candidate, refuted_candidate, proven_infeasible,
  not_found_in_families, numerically_undetermined, need_info. Evidence kinds: bound_violation (check_bounds, or the
  W1 rejection by set_target), atlas_not_found, search_not_found, certificate_undetermined / _refuted / _certified.
  Rule (profile C): PROVEN_INFEASIBLE needs bound_violation; NOT_FOUND_IN_FAMILIES needs atlas_not_found or
  search_not_found (a search over every declared family); UNDETERMINED needs certificate_undetermined; OTHER any
  record except a certified certificate (the outcome follows the record). A record holds only for the spec it was
  computed for (normalized targets and nu; material for certificates; families for atlas and search records).
  `submit(..., evidence=[seq])` cites records; by default every matching record held is cited. The rejection
  message starts "refusal needs evidence: ", names what is needed and lists what is held. Profile B: no check
  (ablation arm), the card says `evidence_checked: false`; an uncertified B release has outcome
  `uncertified_release`.
- Tool schema `amm-tools/2` (`tools.SCHEMA_VERSION`); `schema_version` on the session header, every call record
  and every call output. Schema 2 only adds: tools as_built (C), screen_manufacturing, export; in `evaluate` C
  (6x6), `derived` (cubic constants, Zener ratio, min eigenvalue, E100/E110/E111 from the full tensor,
  Voigt/Reuss averages, eigenvalues; `amm/tensor.py`) and C_MPa; in `certify` the outcome; in `submit`
  outcome_card, submitted.outcome, submitted.evidence; in `get_session` schema_version, evidence (with
  holds_for_current_spec) and the as_built budget. `tools.contract(schema)` gives the versioned contract (argument
  JSON schemas, since, result schema ids); written to `results/software/contract_amm-tools-1.json` and `-2.json`
  (`scripts/software/write_contract.py`).
- Replay: a version-1 log runs in `Session(schema="amm-tools/1")`: current code, results and state hash projected
  to schema 1 (`tools.project`), schema-2 tools not offered. The checker hash is code identity, not a result: if a
  log recorded another checker hash, the replay records the logged one (`identity.checker_aliased`, both hashes
  reported). The refusal rule IS applied: a submit it rejects is a mismatch and is listed in `decision_changes`.
- `outcomes.audit_log(recs)`: static check of a recorded refusal from the logged results (no solves).

### B2 export and as-built
- `certify.as_built_block` = the as-built loop moved out of `certify()` unchanged (certificate hashes identical,
  section 4). Tool `as_built(design, offset=0.01)` (profile C, budget 8 per session): reuses the certificate's rung
  and band index (and its result at the same offset) when the design was certified for the current targets, else
  n = 32 and the band index of the nominal design at n = 20.
- `amm/export.py`: surface = level set 0.5 of the cleaned anti-aliased solid fraction (marching cubes, Lewiner,
  triangles reversed for outward normals; fallback voxel faces); the tiled block is contoured once, so the cells
  merge into one solid. Screening (`amm-screen/1`): minimum solid feature and narrowest channel by morphological
  opening with a ball of diameter L (a centre must lie more than L/2 + 1/2 voxel inside; one voxel of slack on the
  dilation so the surface staircase does not count); pass if at most 1 % of the solid is thinner than the limit;
  estimate = smallest L that removes more than 1 % (bisection to 1/4 voxel). Conservative: convex edges count as
  thin, struts read 1-2 voxels low. Tiled tiles^3 block: one 6-connected piece spanning x, y, z. Watertight: every
  edge in exactly two triangles with opposite orientation; enclosed volume against the voxel volume; shells.
  Printer limit = the material's `min_feature` (a datasheet value) or a stated one. Wording everywhere:
  "manufacturing screening only, NOT a printability claim".
- Tool `export(design, tiles=3, resolution=64, tile_resolution=32, printer_min_feature_mm=None)` writes
  `<session>/exports/<kind>_<spechash8>_<certkey6>/cell.stl, tiled_TxTxT.stl, report.json` (mm when the cell size
  is set). Report `amm-export/1`: spec incl. material values and sources, normalized targets, outcome card
  (certificate outcome for the current targets, else not_certified), certificate summary, last search-tier
  evaluate row (with C*), submission, screening, geometry and file hashes, disclaimers, code and checker identity.
  Deterministic (no timestamp), so a replay reproduces the hashes. No PDF report (JSON only).

### App (GUI) changes, minimal
- `app/toolspec.py` parses the new `since=` decorator argument. `app/backend.py` mirror: schema-2 constants; the
  three new tools are served like the other solver tools (recorded, or a clear mock-mode error); schema-1
  projection; the refusal rule, with the rule itself taken from `amm/outcomes.py` loaded from its source file under
  a private module name (mock mode still never imports amm). `app/mockdata.py` records each log's schema and a
  `replay_compatible` flag (current code, or the pre-B1 code `90f3823f15cbeff4`).
- `tests/test_app.py`: the two mirror tests that selected "sessions written by the current amm code" now select
  `replay_compatible` sessions (after any amm edit no recorded session is current-code; the pre-B1 sessions are
  the ones the contract must still reproduce). No other change there.

### Existing tests changed (the rule they encoded changed)
- `tests/test_tools.py`: the profile-C refusal without evidence is now rejected; the session then records a W1
  bound (gap containing f = 0 rejected by set_target) and refuses; 14 calls instead of 12; checks schema_version.
- `tests/test_bench.py`: profile-C refusals call `check_bounds` first (bound and atlas records); one UNDETERMINED
  refusal moved to profile B (an undetermined certificate costs minutes; the scoring rule tested does not depend
  on the profile). Scoring code (`scripts/bench/scoring.py`) untouched.
- `tests/test_harness.py::test_a1_changes_only_the_harness_file_against_the_plan_time_source`: scripts/bench may
  still differ from the E4 source zip only in e4.py; amm/ may differ only once E4 is scored (RESULT_A2.md exists).
- `tests/test_mutations.py`: `G._SHIFT == 0.0` became `not hasattr(G, "_SHIFT")`.

## 4. Bit-identity check after the edits

`results/software/b1b3_reference_post.json` (log `b1b3_reference_post.log`), same script, same inputs, under the
solver lock, with the edited code (code hash dc9d810c7020a7e9). `python scripts/software/b1b3_reference.py
--compare results/software/b1b3_reference_pre.json results/software/b1b3_reference_post.json`:
- **132 of 132 entries bit-identical** (119 geometry arrays/infos incl. every phase and offset path, 5 C* tensors
  with all scalar outputs, 3 bounds/oracle results, 3 search-tier rows with band arrays on the GPU, 2 full small
  certificates minus the checker field). "DIFFERENT: none".
- MKL CBWR status 65538 before and after (now set lazily).
- Checker identity changed, as it must: f2e482d81382b400 -> f141e46cb67a78db (geometry, bloch, certify and pardiso
  changed; `__init__.py` and `_runtime.py` now part of it).
- Replay of the 5 smoke sessions with the new code: **5/5 exact** (54 calls), now as schema-1 replays (same_code
  false). codex-C-r1-S01 (a certified release) needed the checker alias (log f2e4..., now f141...); no decision
  changed.

## 5. Recorded outcomes that the refusal rule changes

Static audit of every recorded refusal from the logged results (`scripts/software/b1_refusal_audit.py`, output
`results/software/b1_refusal_audit.json`; read only, no solves):

| source | profile C accepted | profile C rejected | profile B (rule not applied) |
|---|---|---|---|
| smoke | 3 | 0 | 8 |
| pilot | 9 | 0 | 12 |
| probe | 2 | 0 | 0 |
| E4 (finished, read only) | 25 | **1** | 134 |

- **Changed: `results/bench/e4/jobs/codex-C-r1-M13`** (E4 confirmatory, arm C). Submitted refuse/UNDETERMINED;
  the session holds a bounded search that found nothing (seq 15, search_not_found) and a refuted certificate
  (seq 16), but no undetermined certificate. Under B1 the submit is rejected; the message lists seq 15 as support
  for NOT_FOUND_IN_FAMILIES and seq 16 for a refuted candidate (verdict OTHER). The E4 scoring is not affected
  (frozen checker and scorer, results untouched); this only says how the new contract would have answered.
- `results/bench/pilot/C/X03` and `results/bench/e4/jobs/codex-C-r1-X11` (PROVEN_INFEASIBLE for a gap containing
  f = 0) are accepted through the W1 record of the rejected `set_target`; without that record they would have been
  rejected, and no agent could have refused such a request at all. Replay of pilot X03 with the new code: the
  submit is accepted (ok matches the log); the other mismatches of that replay come from the older pre-F04 code
  (no budget field, no spec at submission), not from B1.
- The audit is approximate in one respect (it does not re-check the Poisson ratio); `amm.tools.replay` is the
  authoritative check and agreed on the 5 smoke sessions replayed in full and on pilot X03.

Final rerun after the last fix (citing a seq that carries two records, e.g. check_bounds bound + atlas):
`results/software/b1b3_reference_final.json`, `b1b3_compare_final.txt`, final code hash 5970bf55108f1584, checker
f141e46cb67a78db: **132/132 bit-identical, 5/5 smoke replays exact** (C-S01 with the checker alias), no decision
changed.

## 6. Tests

- Full suite (`results/software/b1b3_full_tests.log`, under the solver lock): **144 passed** in 366 s (baseline
  109). New: `tests/test_runtime.py` (12: ordering in fresh interpreters, torch-first error, threads and phases,
  checker closure incl. a synthetic new module, data manifest vs E4 identity, extras, clear errors without BoTorch
  and MCP, CPU fallback), `tests/test_outcomes.py` (15: rule, citations, stale records, family coverage, W1, profile
  B, need_info, five outcomes and contract, schema-1 projection, replay exact / reporting a changed decision,
  checker alias lookup, static audit, tensor summary, C* in evaluate on the GPU), `tests/test_export.py` (7 functions, 8 cases: both
  surface methods watertight, min-feature calibration on sc/bcc struts, screening pass/fail, incomplete without
  cell size, export files + report + determinism, root needed, as_built tool equals the certificate block).

## 7. Not done / open

- No PDF report (the plan says "report JSON/PDF"; the task asked for JSON).
- The GUI mock `evaluate` (atlas rows) has no full tensor; live mode returns amm's. GUI panels are not wired to
  the new tools (B4/B5).
- Licence and Zenodo DOI in the data manifest are left null for the authors (plan B7).
- No clean-environment wheel install test (plan B6).
- The minimum-feature estimate is conservative by about 1-2 voxels (convex edges count as thin); it is a
  screening number, documented as such.
- Rescoring E4 with this code would not accept E4 certificates as current (checker identity changed, as intended);
  the frozen checker is in `C:\AI\AgenticMetamaterials_backups\pre_B1B3_2026-11-07\amm` and the E4 source zip.
