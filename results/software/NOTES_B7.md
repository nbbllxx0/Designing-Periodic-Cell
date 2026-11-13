# B7 log: release build, diagram rule, licences, clean installs (2026-11-08)

Plan item B7 of `plan/SOFTWARE_PAPER_PLAN.md` (and the V9 evidence for table T14). **Nothing was published or
pushed**: no GitHub repository, no `git push` (the folder is not a git repository), no Zenodo upload. The only
network use was the clean installs downloading packages from PyPI and the PyPI/PyTorch CPU index, as in B6. No LLM
calls. No edits to `amm/`, `app/`, `web/src`, `plan/`, `paper/` or `results/verification/`.

Code identity unchanged by B7: `amm.tools.code_hash()` = `f1a6d625064a6d18`, `certify.checker_hash()` =
`c5f8c89871b3bad6` (checked in the staged tree and inside both clean installs).

Backups before editing: `C:\AI\AgenticMetamaterials_backups\pre_B7_2026-11-08\` (pyproject.toml, README.md,
tests/conftest.py).

## 1. What was made

| Item | File |
|---|---|
| Release script | `scripts/release/make_release.py` (allowlist staging, redactions, checks, files.tsv, MANIFEST, sdist + wheel, data bundle, `--selftest`, `--check DIR`) |
| Licence inventory | `scripts/release/licences.py` -> `release/LICENSES.md`, staged `THIRD_PARTY_NOTICES.txt` |
| Staged tree | `release/staging/amm-0.2.0/` |
| Manifest and file list | `release/MANIFEST.md`, `release/files.tsv` (path, bytes, sha256, category, licence) |
| Check results | `release/staged_tree_check.json`, `release/diagram_rule_check.log` |
| Distributions | `release/dist/amm-0.2.0.tar.gz`, `release/dist/amm-0.2.0-py3-none-any.whl` (+ build logs) |
| Data bundle (not uploaded) | `release/data_bundle/amm-data-1/` (7 files of amm-data/1, manifest copy, SHA256SUMS, README) |
| Large files kept out | `release/excluded_large.tsv` (52 STL files with sha256; 8 of them read by F7) |
| Zenodo metadata draft | `release/zenodo.json` (software + data records, DOIs are placeholders) |
| Project files | `LICENSE` (BSD-3-Clause, Shaoliang Yang: **proposed, awaiting the author's confirmation**), `CITATION.cff` (DOI placeholders), `MANIFEST.in` (sdist: tests incl. conftest, docs, examples) |
| Edited | `pyproject.toml` (`license = "BSD-3-Clause"`, `license-files`, `authors`; build requires `setuptools>=77`; no classifier), `README.md` (layout, citation and licence sections), `tests/conftest.py` (one NEEDS entry, section 4) |
| Clean-install evidence | `results/software/b7/` (logs, freezes, identity, `summary.json`, `T14_b7.csv`, run 1 in `run1/`) |

Run (amm env): `python scripts/release/make_release.py` (about 40-80 s), then
`... --selftest` (about 10 min). See `release/MANIFEST.md` for the final counts; the numbers below are from the
build whose wheel the installs used.

## 2. Allowlist and exclusions

Included: `amm/`, `app/`, `web/` (src, dist, index.html, package*.json, tsconfig.json, vite.config.ts; not
node_modules), `docs/`, `examples/` (with outputs, without STL), `tests/`, `bench/`, `.github/workflows/ci.yml`,
`pyproject.toml`, `README.md`, `LICENSE`, `CITATION.cff`, `MANIFEST.in`; scripts `verify/`, `bench/` (frozen E4
harness), `software/`, `ops/`, `paper/` (data plots and tables), and the generators of cited results `atlas/`,
`g2/`, `experiments/`, `probe/`; results `verification/`, `bench/`, `software/`, `g2/`, `probe/`, `gui/`, `atlas/`
(without the data-bundle files), the claims ledger and four cited top-level logs; `paper/figures/*.pdf|png`
(including the F1 render) and `paper/tables/*.md|tex`; `research/related_work.csv` (T1, T10 data).

Which results to include was decided from what the paper cites: the claims-ledger sources, `paper/SUPPLEMENT_data.md`,
and a trace of every file `scripts/paper/make_all.py` opens (audit hook, run on a copy without
`scripts/paper_private/`; `results/software/b7/trace_make_all.py`): 595 files, all staged or in the data bundle,
except the 8 F7 STL files.

Excluded (counts in `release/MANIFEST.md`): `external/` (never walked, nothing in it run), `scripts/paper_private/`,
`plan/`, `pilot/`, `repos_notes/`, `.claude/`, `release/`, `scripts/release/` (the release tool itself names the F1
script it guards against), `scripts/audit/` and `results/audit/` (LLM audit transcripts), `results/speed/` and
`scripts/bench_speed.py` (not cited), `paper/` drafts (README, METHODS, WRITING_GUIDE, ANALYSIS_failures,
SUPPLEMENT_data, CAPTIONS, refs.bib), other `research/` files, caches (`__pycache__`, `.pytest_cache`,
`node_modules`), `web/tsconfig.tsbuildinfo`, all 52 export STL files (241 MB), the 6 data-bundle files of
`results/atlas`, and **3 CLI account-status files** (`results/bench/smoke/jobs/claude-*/claude*/auth.txt`, written by
`amm/llm.py`) that contain the author's e-mail address and organization id. The 326 Codex `auth.txt` files of E4 say
only "Logged in using ChatGPT" and are staged.

## 3. Diagram rule

Assertion `diagram_violations` in make_release.py, run on every staged file and every zip member (also on the sdist
and wheel). It fails the build on: R1 a path under `paper_private`; R2 a non-PDF/PNG file named like the F1 source; R3
a diagram-source format (.drawio, .dot, .mmd, .puml, .tikz, .vsdx, ...); R4 any reference to the private F1 script by name; R5 at
least 3 distinctive lines of the private F1 script (fingerprint held in memory, never written); R6 at least 3 of the
F1 labels in a source file (.py, .tex, .svg, .js, ...); R7 TikZ/PGF in a .tex file; R8 box-and-arrow primitives
(FancyBboxPatch, FancyArrowPatch, ConnectionPatch, graphviz, pydot, schemdraw, ...) in a script; R9 a vector source
(.svg/.eps/.ps) outside `web/`; R10 an unreadable zip.

- Real build: **0 violations**; the F1 render is staged with its hash (MANIFEST). A first build attempt was
  rejected by R6 on `app/outcomes.py` (outcome names shared with F1); the labels are now taken only when they do not
  occur in the package, the GUI, the docs or the data-plot scripts.
- Three staged files named the private script; the staged copies are redacted (exact, counted replacements; source
  files unchanged; table in MANIFEST): `scripts/paper/make_all.py` (the released copy has no hook to the private
  script and keeps the render), `scripts/paper/readme.py` (a dictionary key), `results/claims_ledger.csv|.md` (the
  generating-script field of the 11 F1 numbers; the numbers stay, as frozen data F1 shows).
- Released `make_all.py` works: on a copy of the staged tree plus the data bundle and the 8 F7 STL files it
  regenerates all 71 staged paper files; 61 byte-identical, 10 PDFs differing only in `/CreationDate`
  (`results/software/b7/repro_make_all.json`).
- **Negative test** (`release/diagram_rule_check.log`, not in the staged tree because it names the private script): 9 cases, each
  planted in a fresh temporary staging tree with a full build run; **all 9 fail the build (exit code 1)**, each by
  the planted file only: the private script at its own path (R1 R2 R4 R5 R6 R8), a renamed copy (R4 R5 R6 R8), a copy
  with every name scrubbed (R5 R6 R8), a file that only runs the private script by name (R4), a .drawio file (R3), a TikZ .tex
  (R7), an .svg with the F1 labels (R6 R9), a copy inside a .zip (R5 R6 R8 on the member), a FancyBboxPatch script (R8).

## 4. Clean installs on the current code (T14)

Wheel `amm-0.2.0-py3-none-any.whl`, 111,020 B, sha256
`69025768650ba2ed135c4a807171aeedaa23d54c77e43377b2de07e0ef107484` (built from the sdist, no build isolation,
setuptools 82.0.1, SOURCE_DATE_EPOCH; a rebuild after later tree changes gave the same hash). `AMM_DATA_DIR` pointed
at `release/data_bundle/amm-data-1` in both. Test files: `tests/` and `pyproject.toml` of the staged tree, copied
outside any checkout, so the installed wheel is tested.

| | Windows | Linux |
|---|---|---|
| Environment | fresh venv, Anaconda base Python 3.11.5, Windows 11 | `docker run --rm` python:3.12-slim (image 78976a69c067, the only image used), Python 3.12.16, Debian 13, WSL2 kernel, `--cpus 8 --memory 16g`, no GPU |
| Install | `pip install wheel[all] pytest>=9.0`, PyPI only (PIP_CONFIG_FILE=nul): 178 s | CPU torch from the PyTorch CPU index 38 s, then `wheel[all] pytest` 47 s (run 2) |
| torch / numpy / scipy / mkl | 2.15.0 (CPU) / 2.4.6 / 1.17.1 / 2026.2.0 | 2.15.0+cpu / 2.5.4 / 1.18.1 / 2026.2.0 |
| Identity inside the install | code `f1a6d625064a6d18`, checker `c5f8c89871b3bad6`, CUDA False, MKL CBWR 65538 | same hashes, CUDA False, MKL CBWR 65538 |
| `amm.data.verify(bundle, all roles)` | ok (7/7) | ok (7/7) |
| Tutorial (a) | exit 0, E100 = 0.09541189920967831, checks passed | exit 0, same E100, checks passed |
| `pytest -q -m "not gpu" -rs` | **114 passed, 3 skipped, 1 deselected, 0 failed**, 539 s | **114 passed, 3 skipped, 1 deselected, 0 failed**, 603 s |

Windows test commands ran under the shared lock (`scripts/ops/gpulock_run.py b7 -- ...`, waited for `v10-m13`) with
`CUDA_VISIBLE_DEVICES=-1`; the PyPI Windows torch is a CPU build in any case. The selection is the one B6 and CI use
(`-m "not gpu"`); the deselected test is the GPU band test.

Skips (both platforms, from the logs): `test_b9.py:230` (contracts of schemas 1 and 2 are not next to a wheel),
`test_b9.py:279` (no `results/atlas` in this checkout: the test needs the checkout path, not `AMM_DATA_DIR`),
`test_runtime.py` data-manifest test (needs `results/bench/e4/jobs.json`). With `AMM_DATA_DIR` set the B6 data skips
now run.

**Run 1 found one failure** on both platforms (`results/software/b7/run1/`): 1 failed, 114 passed, 2 skipped, 1
deselected. `test_b9.py::test_contracts_of_schemas_1_and_2_are_unchanged` (added in B9, after B6) is marked `repo`
but had no entry in the conftest table, so it was not skipped when `results/software/contract_amm-tools-1.json` is
absent: FileNotFoundError, not a package defect. Fix: one NEEDS entry in `tests/conftest.py` (no assertion changed).
In the checkout the test still runs and passes (`results/software/b7/checkout_contracts_test.log`: 1 passed). Run 2
is the table above. The Windows venv was deleted afterwards; the container was removed by `--rm` (`docker ps -a`:
none).

Warnings: torch.jit.script FutureWarning (both), and on Linux the scikit-image/NumPy 2.5 deprecation (74 warnings),
as in B6.

**CI has never run on GitHub** (no remote exists; nothing was pushed). These are local clean installs: Windows 11
and a Linux container under WSL2; no native Linux and no macOS run.

## 5. Licences (release/LICENSES.md)

- Project: BSD-3-Clause, proposed. Data bundle: CC-BY-4.0, proposed. Both await the author.
- Python closure of core + extras (from the amm env metadata): no strong copyleft. Flagged as proprietary but freely
  redistributable, not OSI: `mkl`, `onemkl-license`, `tbb`, `tcmlib` (Intel Simplified Software License),
  `intel-openmp`, `intel-cmplr-lib-ur` (Intel EULA), all pulled in by `mkl`/`pypardiso`; amm ships none of them.
  The CUDA torch build of the amm env bundles NVIDIA runtime libraries (the CPU build of the installs does not).
  tqdm is MPL-2.0 AND MIT (weak copyleft, unmodified dependency). umf has an Other/Proprietary classifier but states
  Apache-2.0 with LLVM exceptions.
- web: 191 lockfile packages, 86 production, all MIT/ISC/Apache-2.0/BSD-3-Clause; dev-only `caniuse-lite` is
  CC-BY-4.0. The minified bundle keeps only a few `@license` banners, so `THIRD_PARTY_NOTICES.txt` (licence texts of
  the production packages from node_modules) is staged next to it.
- Vendored code: none (no file of the staged tree is identical to a file of `external/`; amm/homog.py is an
  independent re-implementation of the formulation of the author's MIT registry code).

## 6. Staged-tree checks

All pass on the final tree (`release/staged_tree_check.json`): no paper_private file and no diagram source; no
`external/` path or copy; no secrets (11 token/key patterns: 0 hits); no e-mail address outside the third-party
licence texts; no account details. Absolute user paths: **0 outside frozen records**. In frozen records (results/,
bench/, examples/outputs/, scripts/bench/ launch scripts) they are left unchanged and listed in MANIFEST: on the
final tree 864 occurrences in 35 files (mostly test and solver logs: `results/verification/v3` 302,
`results/verification/v10` 196, `results/atlas/gate_34.log` 73, `results/software/b9` 47, the three
`results/software/b1b3_reference_*.log` 42 each, `results/verification/v4` 41, `results/bench/smoke*` 64,
`results/software/b7` 4, `results/bench/nearmiss.log` 3, `results/verification/v2` 2, one each in
`examples/outputs/04_mcp_client_probe.log` and `results/g2/partial_element_study.log`, and the 4 launch scripts of
the frozen E4 harness `scripts/bench/*.sh`). Launch scripts and READMEs outside frozen records had the author's interpreter path; their
staged copies say `python` / `node` (redaction table).

## 7. Open items for the author

- Confirm the licence (BSD-3-Clause) and the data licence (CC-BY-4.0); `amm/data_manifest.json` still has
  `"license": null, "zenodo": null` (an `amm/` edit; it is not a .py file, so `code_hash()` would not change).
- Repository vs Zenodo: the 8 STL files F7 reads (53.6 MB) and the other 44 export STLs; `results/audit/`
  (excluded); whether `paper/SUPPLEMENT_data.md` (data dictionary) should go with the data or results record.
- Publishing (GitHub, first CI run, Zenodo DOIs) needs the author's approval; then replace the DOI placeholders in
  `CITATION.cff` and `release/zenodo.json`.
- Stale text after B7: `docs/limitations.md` ("No licence has been decided yet"), and the A1 tables T1 ("no LICENSE
  file") and T14 (reads NOTES_B6/B9; B7 numbers are in `results/software/b7/T14_b7.csv`). The ledger in the release
  is the local one with the F1 script name redacted; the A1 run regenerates it.
