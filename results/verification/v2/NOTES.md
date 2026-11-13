# V2: capability and interface acceptance matrix (T12)

Plan item V2 of `plan/SOFTWARE_PAPER_PLAN.md` (claim S1, as corrected by the mid-point review of 2026-11-08: Zener is
a computed output, not a target). amm 0.2.0, tool contract amm-tools/3 (after B9). No LLM calls. Machine: Windows 11,
env `amm`. GPU work only under `python scripts/ops/gpulock_run.py v2 -- <cmd>`, except the live GUI server, which
takes the shared lock per job itself.

## 1. Protocol (written 2026-11-08 07:45, before any row was run)

**Question.** Does every advertised capability work, or get refused correctly, through every interface that
advertises it?

**Interfaces.**

| id | interface | how it is driven |
|---|---|---|
| lib | Python library | `amm.tools.Session(dir).call(...)` |
| mcp | MCP server | `python -m amm.mcp_server --session DIR --profile P`, driven by an MCP client with no LLM (`mcp.ClientSession`, as in examples/04); raw JSON-RPC over stdio for malformed input |
| gui | live GUI, HTTP API | `python -B -m app.server --live --port 8767 --root results/verification/v2/sessions/gui`; `POST /api/tools/{name}` with `wait`; one GUI session per scenario (`POST /api/session/new`) |
| gui-edge | live GUI, browser | `app/e2e_live.py` (headless Edge, temporary profile, CDP on 127.0.0.1) against the same server: every action is a click |
| cli | command line | `python -B -m amm.cli` (the `amm` console script). It did not exist: added in V2 (section 2) |

**Rows.** `scripts/verify/v2/matrix_spec.py` holds the scenarios. Each checked step is one row per interface. Its
expectation is a list of predicates on the call output `{ok, seq, result | error}`, and it is the same for every
interface. `expectations.csv` (390 rows) and `expectations_transport.csv` (19 rows) list them all, written before
the run. Coverage:

1. Target types, each with a feasible and an infeasible spec: density, E100, G, bulk, nu100, complete gap. The
   combinations are stiffness + gap (+ density), and density + stiffness (S01, S11, S13).
2. Families: tpms, struts and resonators, each alone and all together. The checks are atlas verdicts, the
   suggestion kinds, `n_cells` per family, and one `evaluate` per family (S04).
3. Materials and units: all four materials of `amm.units.MATERIALS` and a custom material. The units are GPa, MPa
   and kHz with a cell size, and normalized `E_s` against GPa. Hz without a cell size and GPa without a material
   must give UNDERSPECIFIED or need_info. A material change mid-session must flip the verdict of the same physical
   target (S02, S03).
4. Invalid requests: an unknown target, Zener as a target (it must be refused with a message that says Zener is an
   output), negative and contradictory bounds, an out-of-box parameter, a validity-rule violation, an unknown kind
   or family, wrong types and units, an unknown tool, malformed JSON (MCP, GUI API and CLI), and budget exhaustion
   (five certificates, cap 4) (S01, S05, S10, transport).
5. Stale certificates: after a spec edit, a material change and a design change, the old certificate must not
   support a release. `submit` must refuse it, `get_session` must show `holds_for_current_spec` false, and export
   must say not_certified. This is checked for a static certificate (S11: mcp, gui) and a stiffness + gap
   certificate (S13: lib). Stale refusal evidence (bound, atlas and undetermined records) is checked in S08, S09
   and S14.
6. Export and screening: single-cell and tiled export (1x1x1, 2x2x2, 3x3x3), and screening pass and fail at two
   printer limits. report.json must reference the certificate (verdict and `certify_seq`) after a certified
   release, and must have `certificate: null` when there is none (S11, S12, S13).
7. Outcomes: certified_candidate (S11, S12, S13, Edge), refuted_candidate (S10), proven_infeasible (S08, Edge),
   not_found_in_families (S09), numerically_undetermined (S14) and need_info (S03). In profile B (S06, S07), a
   refusal without evidence is accepted with `evidence_checked` false, and a release without a certificate gets
   `uncertified_release`. In profile C, both are rejected (S08, S15).
8. Replay: `amm.tools.replay` must reproduce every session log V2 writes, and `amm replay` must too (CLI row).

**Sources of the expectations.** These are listed in the header of `matrix_spec.py`. They are: the documented
contract, the bounds of `amm/bounds.py` with the limits worked out by hand, the material table, facts read from the
atlas files before the run, the recorded E4 certificates of the reused designs (M03: combined, certified in 150 s;
G05: gap, undetermined in 122 s), and tutorials 02 and 03. No tool call was made to set an expectation. Where the
docs allow more than one answer, the expectation lists the set: FEASIBLE or BORDERLINE for the struts-only gap and
for the combined spec.

**Keeping the run small.** Fresh certificates:

- S13: 316L stiffness + gap, about 150 s.
- S14: Ti6Al4V gap, undetermined, about 120 s.
- S11 (mcp, gui) and S12 (cli): the same PA12 static design, about 20 s each. The spec and design are identical,
  so the certificate key is the same, and the three results are compared with one another.
- The Edge pass: a 316L struts static certificate, about 45 s, plus one run that is cancelled.
- S10 (lib, mcp, gui): four certificates per interface of non-percolating cells. These are geometry-only refutations
  plus the as-built check, so only seconds each. They are needed for the refuted outcome and for budget
  exhaustion.

**Pass rule.** A row passes when every predicate holds. A row whose expectation is a refusal and which is refused
as expected counts as "refused as expected". When a row fails because of an amm bug, the bug is recorded. It is
fixed only if the fix is small and local. Then `scripts/software/b1b3_reference.py` must be bit-identical with
`b1b3_reference_final.json` (132 entries, timing and checker fields excluded), and the full test suite must pass
under the lock. Every amm change is logged in `results/software/NOTES_V2_fixes.md`.

**Probe before the fix pass.** The invalid-request scenario S01 is first run on the library alone
(`--tag probe`, `sessions/probe/`), so the behaviour before any fix is on record. Rows whose message changes with a
fix are then expected to fail replay of the probe log at exactly those calls. This is reported, not hidden.

## 2. The CLI (added in V2)

amm had no command line before V2: pyproject.toml had no `[project.scripts]`, and `amm/llm.py` is the LLM runner,
not a user CLI. V2 adds `amm/cli.py` (`[project.scripts] amm = "amm.cli:main"`) with the subcommands check-bounds,
atlas-suggest, evaluate, certify (`--release`, `--export`), export and replay. Each one builds the list of tool calls
(set_material, set_constraints, set_target, then the tool) and passes the values unchanged to `Session.call`. It
prints one JSON object and stops at the first failed call. The exit status is 0 when every call is ok, 1 when a
call is refused, and 2 for a usage error. Tests: `tests/test_cli.py`. Docs: `docs/quickstart.md`.

The installed environment still has amm 0.1.0 registered (an editable install from before the extras). Nothing was
reinstalled, so the `amm` console script itself does not exist in this environment. Every CLI row runs
`python -B -m amm.cli`, which runs the same `main`. A test checks that the pyproject entry resolves to that
function.

## 3. Run log

| when (2026-11-08) | step | where |
|---|---|---|
| 07:45 | protocol and expectations written (`expectations.csv`, `expectations_transport.csv`) | this file, section 1 |
| 07:50-07:57 | **probe** (code before the V2 fixes, `e0350cf7efa454b0`): S01, S10 and S03 on the library | `observations/probe/`, `sessions/probe/`, `probe_rows.csv` |
| 07:58 | V2-2 to V2-4 fixed in amm (code `f1a6d625064a6d18`; checker unchanged, `c5f8c89871b3bad6`) | `results/software/NOTES_V2_fixes.md` |
| 08:17-08:51 | run 1: lib, mcp, cli (one lock hold) | `logs/run_lib_mcp_cli.log` |
| 08:25 | addendum S16 and S17 defined (`expectations_addendum.csv`), before it was run; see 4.2 | `matrix_spec.py` |
| 08:51 | addendum on lib, mcp, cli; MCP transport rows | `logs/run_addendum.log`, `logs/run_special_mcp.log` |
| 08:52-09:02 | live GUI server (port 8767, `--root sessions/gui`): every GUI scenario through the HTTP API, the transport rows, then the headless-Edge pass (`app/e2e_live.py`, screenshots in `shots/`). The server was stopped through `/api/shutdown` (exit 0) | `logs/run_gui_phase.log`, `sessions/gui_edge/e2e_live_20261108-090158.json` |
| 09:03 onward | one lock hold: replay of every V2 log, the bit-identity reference, the full test suite | `logs/final_checks.log`, `replays.csv` |

The probe was run before any fix, as planned. It found three amm bugs: `negative_G_min`, `zener_target` and
`hz_partial_check` (`probe_rows.csv`, 33/36 rows pass). They were fixed (V2-2 to V2-4) before run 1, so every main
row ran on the fixed code.

## 4. Results

### 4.1 Totals

`matrix.csv` has 443 rows: one per (capability check x interface), plus one replay row per interface. 159 distinct
checks.

| interface | pass | refused as expected | fail |
|---|---|---|---|
| lib | 66 | 37 | 10 |
| mcp | 71 | 39 | 9 |
| gui (HTTP API) | 71 | 41 | 10 |
| gui-edge (clicks) | 5 | 1 | 0 |
| cli | 54 | 26 | 3 |
| **all** | **267** | **144** | **32** |

Of the 32 failures:

- **31 are V2 expectation or design errors.** A pre-defined expectation was wrong, a test design was wrong, or the
  failure is a cascade of one. amm was correct in each case. Section 4.2 has the details.
- **1 is an app/ bug** (`gui_health`), outside the V2 edit scope. Section 4.3.
- **None is an amm bug.** The three amm bugs V2 found were found by the probe and fixed before run 1 (section 3).

Every failed row is kept in the matrix, with its cause in the `cause` column (`failure_causes.json`). Rows whose
expectation was wrong were re-run in the addendum (S16, S17) with a corrected expectation, written before they ran,
and all 30 addendum rows pass. `T12_v2.csv` gives the counts per capability group and interface, with the
failures split by cause.

### 4.2 Failures from V2 expectation or design errors (amm correct)

| rows | what happened | correction |
|---|---|---|
| `fam_tpms_bounds` (4 interfaces), `S09 nf_bounds` (3) | the expectation was NOT_FOUND_IN_FAMILIES for a tpms-only gap f* [0.25, 0.35], below every tpms gap in the atlas. amm says BORDERLINE: the oracle counts the optimistic error range and the interpolation between cells (`amm.atlas.oracle`), and the expectation ignored both. `n_cells` counts only cells inside the calibrated domain (216 tpms, 2714 in all), not the rows of the file | S17 with gap f* [2.5, 3.0] and families tpms + struts: NOT_FOUND on all four interfaces |
| `fam_all_bounds` (4) | the same `n_cells` mistake. The verdict predicate (FEASIBLE) held | none needed |
| `validity_rule` (4) | the test design cube_bars c 0.5, w 0.48 is outside the box (w <= 0.36), so the box message came first. That is a correct refusal with a different message | S16 `validity_rule_r2` (c 0.35, w 0.33): "violate the family's validity rule" on all four interfaces |
| `S08 wrong_verdict` (3) and its cascades `unknown_evidence_seq`, `proven_infeasible` (3 + 3) | check_bounds of a spec that violates a bound also holds an atlas NOT_FOUND record (documented in tests/test_outcomes.py), so refuse NOT_FOUND_IN_FAMILIES was rightly accepted, with outcome not_found_in_families. The later submits then met "already submitted" | S16: refuse UNDETERMINED is rejected, an unknown seq is rejected, and proven_infeasible cites the bound record (lib, mcp, gui) |
| `S09 nf_holds`, `not_found_in_families` (3 + 3) | cascades of `nf_bounds`: no atlas record was held, so the refusal was rightly rejected. In run 1, `stale_family_record` passed only vacuously | S17 `stale_family_record_r2`, `nf_holds_r2`, `not_found_in_families_r2` (lib, mcp, gui) |
| `combo_export` (lib) | wrong path: report.json `certificate.gap.verdict` is the verdict object `{"verdict": "certified"}`, the same shape as the certify result's `gap.verdict` (which `combo_certify` read correctly) | the corrected predicate holds on the same report.json (`posthoc_checks.json`), with `certify_seq` 6 = the certify call and outcome certified_candidate |

### 4.3 Failure from an app/ bug (not fixed: outside the V2 edit scope)

`gui_health`: in live mode, `GET /api/health` reports `schema` = `app/backend.SCHEMA_VERSION`. That is the
mock mirror's "amm-tools/2", which NOTES_B9 already lists as stale. The live session itself is amm-tools/3. The
`code` shown, `ff8b3a682221f9a3`, comes from `app/mockdata.code_hash()`, whose `NOT_HASHED` mirror lacks `cli.py`
since V2-1, so it no longer equals `amm.tools.code_hash()` (`f1a6d625064a6d18`). The fix belongs in app/: add
`"cli.py"` to `app/mockdata.NOT_HASHED`, and report the live session's schema in live mode. The GUI session logs
are written by amm and carry the correct identity: all 19 replay exactly.

### 4.4 What the rows show (all interfaces unless stated)

- **Target types.** Every type was checked with a feasible and an infeasible spec. FEASIBLE: density, E100 (GPa
  and E_s give the same normalized value to 1e-15), G, bulk, nu100 and gap. Infeasible: density_min 0.9 is
  NOT_FOUND; E100, G and bulk give PROVEN_INFEASIBLE by V1; nu100_min 0.6 by S1; a gap above every atlas gap is
  NOT_FOUND; a gap containing f = 0 is refused on input (W1). Combinations: stiffness + gap + density gives
  BORDERLINE (within its expectation set); E100 0.5 E_s + gap gives PROVEN_INFEASIBLE; and density + stiffness in
  MPa (PA12) is FEASIBLE and then certified.
- **Families.** Suggestions for tpms only, struts only and resonators only contain only that family's kinds.
  `n_cells` is 216 / 1395 / 1103 / 2714. `evaluate` of one design per family returns the 6x6 C\* and the Zener
  ratio as an output.
- **Materials and units.** All four materials: E, nu and atlas availability are right (AlSi10Mg, nu 0.33: atlas
  UNAVAILABLE with the reason). GPa, MPa and kHz with a cell size convert to 1e-12 of the hand values. A custom
  material works, nu >= 0.5 is refused, and an unknown name is refused. The material change mid-session: 5 GPa is
  0.026 E_s on 316L (no bound violated) and 2.94 E_s on PA12, which gives PROVEN_INFEASIBLE by V1.
  UNDERSPECIFIED: GPa without a material, and Hz without a cell size, are named in `cannot_normalize`. check_bounds
  is refused when nothing can be normalized, and is UNDERSPECIFIED when part of the request can be (after V2-4).
  certify is refused. submit(need_info) gives need_info.
- **Invalid requests**, all refused with a message naming the problem: an unknown target; Zener as a target
  ("not a design target: ... computed outputs", after V2-2, CLI included); a negative minimum (after V2-3);
  contradictory bounds and negative maxima (PROVEN_INFEASIBLE by P1); an unknown unit, a wrong type, an
  out-of-box parameter, a validity rule, a TPMS design without a mode, an unknown kind or family, an empty family
  list, more than 16 designs, top out of range, a negative cell size and an unknown tool. A second submit is
  refused, and so is a release without a design. Budget exhaustion: the fifth certificate is refused with "session
  budget exhausted: 4 of 4 certify used" (lib, mcp, gui). No rejected call spends budget. Malformed JSON:
  - **MCP:** a non-JSON line gets no reply. The server stays up, nothing is logged, and the next call is answered.
    `arguments` that is not an object gets JSON-RPC -32602. A wrong type comes back isError and is logged with ok
    false.
  - **GUI API:** HTTP 400 "body must be JSON", 400 for "JSON object", 415 for a wrong content type, 403 for a
    foreign Host and 400 for a bad actor. seq is unchanged in each case.
  - **CLI:** exit 2 with "not valid JSON".
- **Stale certificates.** After a spec edit, a material change or a design change, `submit(release)` refuses the
  old certificate ("release needs a certificate ... for this design and the current targets"). `get_session`
  shows `holds_for_current_spec` false. An export after the edit says not_certified, with `certificate: null`.
  After `undo`, the record holds again and the release is accepted. This was checked for the static PA12
  certificate (mcp, gui) and for the stiffness + gap certificate (lib). Stale refusal evidence is rejected for a
  bound record after a spec edit, an atlas record after widening the families, and an undetermined certificate
  after a gap edit.
- **Certificates.** Five verdict paths were exercised:
  - S13 (316L, 5 mm, 3.53 GPa + 174-271 kHz + density): **certified**, gap certified.
  - S14 (Ti6Al4V gap): **undetermined** ("count failures").
  - S10: four non-percolating schwarz_p cells **refuted** (invalid geometry) on each of lib, mcp and gui.
  - PA12 static: **certified** (mcp, gui, cli).
  - Edge: 316L struts **certified**.

  The PA12 certificate is identical through MCP, GUI and CLI: the same result hash, `d47062dbaab89457`, and the
  same certificate key and file, `c3816dab1e980508_c79d2f3892e37426.json`. It is also identical to the one
  tutorial 02 recorded before B9 (`cert_consistency.json`). `as_built` reuses a held certificate without a new
  solve or budget.
- **Export and screening.** Single cell plus tiled 1x1x1, 2x2x2 and 3x3x3. Screening passes at the material's
  default limit and fails at a stated larger limit (PA12 at 0.8 vs 3.0 mm; 316L at 0.3 vs 1.0 mm). The CLI case
  is bcc at 10 mm vs 4 mm. After a certified release, report.json references the certificate (`certificate.verdict`
  certified and `certify_seq` = the certify call), the outcome and the submission. Without a certificate it has
  `certificate: null` and outcome not_certified. An export without a session directory is refused (CLI).
- **Outcomes**, each reached through at least one interface:

  | outcome | interfaces |
  |---|---|
  | certified_candidate | lib, mcp, gui, gui-edge, cli |
  | refuted_candidate | lib, mcp, gui |
  | proven_infeasible | lib, mcp, gui (S16), gui-edge |
  | not_found_in_families | lib, mcp, gui (S17; also S08 run 1) |
  | numerically_undetermined | lib |
  | need_info | lib, mcp, gui |

  Profile B: no check_bounds, certify or as_built (14 tools in lib, mcp and gui; refused on the CLI). A refusal
  without evidence is accepted with `evidence_checked` false. A release without a certificate gets
  uncertified_release. Profile C rejects both ("refusal needs evidence", "call certify first"); the Edge pass shows
  the same in the browser.
- **GUI clicks (Edge).** Every action in the Edge pass was a click:
  - Certify was cancelled while running. It was rolled back: seq 9 stayed 9, and the certify budget stayed 0.
  - Certify again: certified in 214.5 s; release then gave the outcome card.
  - Screening passed. The export gave certified_candidate, and the STL, report.json and zip downloads were valid.
  - A refusal without evidence was rejected with the message shown. After Check bounds, proven_infeasible cited
    the bound record.

### 4.5 Replay

`replays.csv`: **170 of 170 V2 logs replay exactly**:

| interface | logs | calls compared | certificates re-run | exports re-run |
|---|---|---|---|---|
| lib | 15 | 185 | 6 | 2 |
| mcp | 16 | 182 | 5 | 2 |
| gui (incl. the 2 Edge sessions) | 19 | 200 | 6 | 3 |
| cli | 120 | 370 | 1 | 3 |

The comparison covers ok, state hash and full result, including the sha256 of every exported file. The CLI row
`cli_replay` also runs `amm replay` on the CLI certificate session (exit 0, exact).

The 3 probe logs were written by the code before the fixes. One replays exactly (S10). The other two differ at
exactly the fixed calls, as planned:

- probe S01, seq 41: the negative G_min is now refused. That changes the state hash of the following calls.
- probe S01, seq 44: the Zener message.
- probe S03, seq 7: UNDERSPECIFIED.

### 4.6 GPU time and incidents

- **Certificates with an FE solve:** S13 247 s, S14 231 s, PA12 26 s (mcp), 75 s (gui) and 30 s (cli), and Edge
  215 s (+ 8 s cancelled). Six in all, as planned. Plus 16 geometry-only refutations (S10 in lib, mcp and gui, and
  the probe), 15-40 s each, mostly the as-built check. The certificate times were up to 1.7 x the recorded E4
  times (S13: 247 vs 150 s) because of the contention described below.
- **Lock-held wall time:**
  - probe 1.5 min;
  - run 1 34.5 min, including a 15.5 min stall of one CLI `evaluate`;
  - GUI jobs about 8 min (the server took the lock per job);
  - replay 19.4 min and bit-identity reference 9.2 min;
  - test suite 6.8 min, plus a 0.3 min rerun (section 5).

  Total about 87 min, against the target of about 45. The excess is the stall, the replay (it re-runs every
  certificate) and contention-inflated solves.
- **Incident: the solver lock did not serialize V2 and V6.** At 08:17 V2 held the lock (gpulock_run pid 29476). At
  08:33:51 a V6 `gpulock_run` (pid 50636) and its child started at once, and at 08:33:54 V6's `recheck.py` (pid
  28208) wrote the lock file, all while V2's holder was alive. At 07:51, before V2 ran, two V6 jobs (74236 and
  78496) also ran at the same time. GPU utilization was 100 % and 23.9 GB in use while V2 ran. The likely cause is
  that `scripts/ops/gpulock_run.py` releases with an unconditional `unlink()`: any holder that exits deletes the
  current lock file, even one written by another process (`app/live.GpuLock.release` checks the owner first). Some
  V6 scripts also run on the GPU without the lock (recheck.py, a GUI server on port 8768). This was not fixed:
  scripts/ops is outside the V2 scope. V2 results do not depend on it, since every replay, the cross-interface
  certificate identity and the bit-identity reference are exact, but the timings are inflated.
- **Lock starvation:** V2 first waited about 25 min with the 2 s polls of gpulock_run while V6 re-took the lock.
  `scripts/verify/v2/lockwait.py` waits for the file to disappear (10 ms polls) and then starts gpulock_run
  unchanged. Every V2 GPU job ran through gpulock_run, or through the GUI server's own per-job lock.

## 5. amm changes, bit identity and tests

- amm changes V2-1 (CLI, `cli.py` in `NOT_HASHED`) and V2-2 to V2-4 (three small local fixes found by the probe)
  are logged in `results/software/NOTES_V2_fixes.md`. Code identity is `f1a6d625064a6d18`; the checker identity,
  `c5f8c89871b3bad6`, is unchanged.
- Bit-identity reference after the fixes: 132 of 132 arrays and dicts are identical to
  `results/software/b1b3_reference_final.json`, excluding timing and checker fields ("DIFFERENT: none"). The 5
  smoke replays are exact (`logs/v2_compare.txt`). It ran in 9.2 min under the lock.
- Full test suite under the lock: 174 passed, 1 skipped, in 6.7 min (`logs/full_tests.log`). The skipped test is
  `test_live_backend_end_to_end`: it found the lock file naming another live process while V2 held the lock (the
  incident in 4.6). Rerun alone under the lock, it passed in 14 s (`logs/live_test_rerun.log`). Total lock time,
  including this rerun, about 87 min.

## Post-V2 fixes (lead, 2026-11-08)

- `gui_health` row: `app/server.py` `/api/health` now reports `amm.tools.SCHEMA_VERSION` and `amm.tools.code_hash()` in live mode (mock mode keeps the mirror's amm-tools/2); `app/mockdata.NOT_HASHED` now includes `cli.py`, so the mirror hash equals amm's (f1a6d625064a6d18). 28 app/cli tests pass. The V2 matrix row stays `fail` as recorded.
- Lock incident: `scripts/ops/gpulock_run.py` released with an unconditional `unlink()`. `__exit__` now removes the lock only when it holds our own pid (self-test: own lock released, foreign lock kept). V6 processes started before the fix still use the old release. `scripts/bench/e4.py` (frozen E4) was not changed.
