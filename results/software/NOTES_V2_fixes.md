# V2 log: amm changes made during the capability and interface acceptance matrix (2026-11-08)

Every change to `amm/` during V2 (`results/verification/v2/NOTES.md`), with the method of `NOTES_B9.md`. No LLM
calls. No edits to `scripts/bench/`, `results/bench/`, `plan/`, `scripts/paper/`, `paper/`, other
`results/verification/` folders or V6 files. GPU runs only under `python scripts/ops/gpulock_run.py v2 -- <cmd>`.

## 0. Before editing

- Identity at the end of B9: `amm.tools.code_hash()` = `5ab7480410467482`, `certify.checker_hash()` = `c5f8c89871b3bad6`.
- Backup: `C:\AI\AgenticMetamaterials_backups\pre_V2_2026-11-08\` holds `amm_after_cli/` (amm/ after V2-1, before
  V2-2 to V2-4), plus pyproject.toml, tests/conftest.py, docs/quickstart.md and docs/index.md. The B9-final
  tools.py differs from `amm_after_cli/tools.py` only in the `NOT_HASHED` lines of V2-1.

## 1. Changes

| id | file | change | why |
|---|---|---|---|
| V2-1 | `amm/cli.py` (new), `amm/tools.py` `NOT_HASHED`, `pyproject.toml` `[project.scripts]` | the command line (`amm = "amm.cli:main"`): check-bounds, atlas-suggest, evaluate, certify (`--release`, `--export`), export, replay; JSON output; no logic of its own. `cli.py` is added to `NOT_HASHED`, like `mcp_server.py`: it is a transport and does not determine any tool result, so later CLI edits do not change the code identity | S1 claims a command line; amm had none |
| V2-2 | `amm/tools.py` `_call` (+ `OUTPUT_QUANTITIES`, `_output_hint`) | a `set_target` key that names a computed output (zener*, anisotropy*, C11/C12/C44*, E110*/E111*, cubic_deviation, min_eig) is still refused by the argument model, and the message now adds the reason: "zener_min: not a design target: the Zener ratio, the cubic constants C11, C12, C44 and E110 / E111 are computed outputs of evaluate (results[].derived), never targets or certified quantities. Targets: ...". Any other unknown key keeps the plain pydantic message | V2 row `zener_target` (probe): the refusal said only "zener_min: Extra inputs are not permitted", which does not tell the user that Zener is an output (mid-point review, S1) |
| V2-3 | `amm/tools.py` `set_target` | `E100_min`, `G_min` or `bulk_min` <= 0 is refused on input: "G_min must be positive: a minimum modulus <= 0 constrains nothing (bound P1); leave it out". Maxima are unchanged (E100_max <= 0 stays PROVEN_INFEASIBLE by P1) | V2 row `negative_G_min` (probe): `amm/bounds.py` documents P1 as "requested minima must be positive where the quantity is a modulus", but only `E100_max` was checked. A negative minimum was accepted and reported FEASIBLE, so it could be "certified" as a vacuous target |
| V2-4 | `amm/tools.py` `check_bounds` | the top-level `verdict` is `UNDERSPECIFIED` while a target cannot be normalized (`cannot_normalize` not empty), unless a bound is violated. The atlas verdict of the part that can be normalized stays in `atlas.verdict` | V2 row `hz_partial_check` (probe): with a gap in Hz and no cell size plus `density_max`, the top-level verdict was `FEASIBLE` (the atlas verdict of `density_max` alone), while `bounds_verdict` was `UNDERSPECIFIED`. A request that cannot be stated in solver units must not be reported feasible |

Scope checks before V2-2 to V2-4: 360 recorded session logs outside V2 (results/, examples/, pilot/, bench/,
including every E4 job) were scanned. None calls `set_target` with a minimum <= 0, none has a `check_bounds` result
with a non-empty `cannot_normalize`, and none sets a target whose key names an output. So no recorded decision or
result changes, and frozen-E4 and development replays are not affected. Tool docstrings were not changed: the
contracts of schemas 1 and 2 are frozen byte for byte (`tests/test_b9.py`), and they hold the docstrings.
**Follow-up (outside the V2 edit scope):** the `check_bounds` docstring and `docs/tool_contract.md` list the verdicts
PROVEN_INFEASIBLE, NOT_FOUND_IN_FAMILIES, FEASIBLE and BORDERLINE. They should also name UNDERSPECIFIED for a request
that cannot be normalized yet. `docs/concepts.md` could say that minima must be positive.

Tests: `tests/test_cli.py` (7), `tests/test_v2_fixes.py` (3); `tests/conftest.py` gains one `repo:pyproject.toml`
entry.

## 2. Verification

- **Identity after V2:** `code_hash()` = `f1a6d625064a6d18` (B9: `5ab7480410467482`; after V2-1 alone: `e0350cf7efa454b0`).
  `checker_hash()` = `c5f8c89871b3bad6`, unchanged. Replay aliases code and checker identities as before, so every
  earlier log still replays (see below).
- **Bit identity:** `scripts/software/b1b3_reference.py` was re-run after all four changes, under the lock, and
  compared with `results/software/b1b3_reference_final.json`. 132 arrays and dicts were compared, and the result is
  "DIFFERENT: none". Timing fields are excluded, and so are the checker identity fields, as in B9: the final
  reference records the B1-B3 checker hash `f141e46cb67a78db`. All five smoke replays inside the reference are exact,
  before and after (codex-B-r1-S01, codex-C-r1-N01, N02, S01 and X01). Log:
  `results/verification/v2/logs/v2_compare.txt`. The result JSON is `logs/v2_reference_post.json`.
- **Replay:** all 170 V2 session logs (lib, mcp, gui incl. Edge, cli) replay exactly on the fixed code
  (`results/verification/v2/replays.csv`). The 3 probe logs, written before V2-2 to V2-4, differ exactly at the
  calls the fixes change: S01 seq 41 (V2-3) and seq 44 (V2-2), and S03 seq 7 (V2-4).
- **Tests:** full suite under the lock, `pytest -q -rs`: **174 passed, 1 skipped** in 405 s (`results/verification/v2/logs/full_tests.log`). The skip is `test_app_live.py::test_live_backend_end_to_end`. It skipped because the lock file named another live process while V2 held the lock: the lock incident of V2 NOTES 4.6. Rerun alone under the lock: 1 passed in 14 s (`logs/live_test_rerun.log`). So 175 of 175 pass.
  The 10 new tests are in `tests/test_cli.py` and `tests/test_v2_fixes.py`, and
  `tests/test_bench.py::test_code_hash_ignores_oracle_runner_and_transport` now expects `cli.py` in `NOT_HASHED`.

**Follow-ups outside the V2 edit scope (reported, not fixed):**

1. `app/mockdata.NOT_HASHED` lacks `cli.py`, so `/api/health` shows code `ff8b3a682221f9a3`, not `f1a6d625064a6d18`.
   The schema `app/backend.SCHEMA_VERSION` still says amm-tools/2, while live sessions are amm-tools/3. This is V2
   row `gui_health`.
2. The `check_bounds` docstring and `docs/tool_contract.md` should name UNDERSPECIFIED (V2-4), and
   `docs/concepts.md` should say that minima must be positive (V2-3). This requires a schema 4 decision, because the
   docstrings of schemas 1 and 2 are frozen.
3. `scripts/ops/gpulock_run.py` releases the lock with an unconditional `unlink()`, so one holder can delete
   another's lock. During V2, V6 jobs ran on the GPU while V2 held the lock (`results/verification/v2/NOTES.md`
   4.6). It should check the owner, like `app/live.GpuLock.release`.
