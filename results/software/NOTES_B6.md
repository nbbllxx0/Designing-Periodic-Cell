# B6 log: docs, tutorials, CI, clean install (2026-11-08)

Plan item B6 of `plan/SOFTWARE_PAPER_PLAN.md`. No LLM calls. No edits to `amm/`, `app/`, `web/`, `scripts/bench/`,
`results/bench/`, `results/verification/` or `plan/`. Code identity unchanged: `amm.tools.code_hash()` =
`5970bf55108f1584`, `certify.checker_hash()` = `f141e46cb67a78db`, the same as at the end of B1-B3.

Backup before editing: `C:\AI\AgenticMetamaterials_backups\pre_B6_2026-11-08\` (pyproject.toml, README.md, tests/).

## 1. Produced

- `docs/` (Markdown):
  - `index.md`, `install.md`, `quickstart.md`, `concepts.md`, `tool_contract.md`, `mcp.md`, `gui.md`,
    `extending.md`, `data.md`, `limitations.md`;
  - `gen_tool_reference.py`, which generates `tool_contract.md` from `amm.tools.contract()` and has a `--check`
    mode for CI. The live contract equals the frozen `results/software/contract_amm-tools-2.json`.
- `examples/`:
  - `01_evaluate_tensor.py` (tutorial a), `02_atlas_to_certificate.py` (tutorial b), `03_export_and_screening.py`
    (tutorial c);
  - `04_mcp_client_probe.py`, an MCP stdio client with no LLM, used to verify `docs/mcp.md`;
  - logs in `examples/outputs/`, and `examples/outputs/.gitignore` for `*.stl`.
  - No `.ipynb` versions: `nbformat` is not installed in the `amm` env, and it was not installed.
- `.github/workflows/ci.yml`: CPU-only, windows-latest and ubuntu-latest, Python 3.11.
- `tests/conftest.py`: markers and automatic skips. No test file and no assertion was changed.
- `pyproject.toml`: `readme = "README.md"` and the pytest markers `gpu`, `data`, `repo` and `slow`.
- `README.md`: rewritten as the project front page. No badges, because there is no remote and so no real badge
  URL. It has a citation placeholder and "Licence: to be decided (B7)"; no LICENSE file exists.

Every command written in the docs was run, except one kind:

- the Claude Code and Codex client configurations in `docs/mcp.md`. Running them means LLM calls. They are the
  forms `amm/llm.py` generated for the benchmark runs, and the server side was verified with the probe.

The Python snippets of `docs/quickstart.md` and `README.md` were extracted and run verbatim (under the solver
lock), with the outputs stated in the comments: FEASIBLE / certified certified_candidate / certified_candidate,
and replay `True 12`. The `docs/extending.md` snippet was run, and its output is pasted there.

## 2. Tutorials (recorded runs)

| Tutorial | Environment | Wall time | Result |
|---|---|---|---|
| (a) `01_evaluate_tensor.py` | amm env, RTX 4090, under `gpulock_run.py b6` | 7 s (script 4.6 s; evaluate 2.0 s) | gyroid sheet 0.25 on Ti6Al4V: C* printed, E100 = 0.09541 E_s = 10.86 GPa, Zener 1.137, checks passed |
| (a) | clean venv, CPU-only torch 2.15.0+cpu | 17 s (evaluate 14.2 s) | same printed tensor (5 digits). E100 differs in the 16th digit (0.09541189920967828 vs ...831): other numpy/scipy/MKL builds |
| (b) `02_atlas_to_certificate.py` | amm env, under the lock | 25 s (certify 20 s) | PA12, 10 mm, E100 >= 25 MPa, density <= 0.25: check_bounds FEASIBLE (892 of 2714 atlas cells clear the targets pessimistically); suggestion sphere_ligaments c 0.12, w 0.1817; certificate certified, robust; guarded E100 lower bound 45.9 MPa; release accepted as certified_candidate; replay of the log exact (12/12) |
| (c) `03_export_and_screening.py` | amm env (CPU only) | 21 s | bcc r 0.08: screen passed at 10 mm (min feature 1.56 mm vs 0.8 mm), failed at 4 mm (0.62 mm, 83.9 % of the solid thinner than the limit); export of cell and 3x3x3 STL (marching cubes, 37,964 and 225,140 triangles) and report.json; outcome not_certified |
| (c) | clean venv | 19 s | same verdicts and file names |
| MCP probe `04_mcp_client_probe.py` | amm env and clean venv | about 2 s | 17 tools (profile C); check_bounds names V1; an invalid call is rejected (`is_error` true) |

GPU use under the lock: tutorial (a) 7 s, tutorial (b) 25 s, the docs snippets 96 s (wall time, mostly CPU
certificates), and the final test suite (section 6). That is well under the 20 GPU-minute budget.

**Incident.** The first run of the full suite (to measure per-test durations) was meant to be CPU-only through
`CUDA_VISIBLE_DEVICES=""`. On Windows an empty environment variable is removed, so CUDA stayed visible, and that
run (275 s, 144 passed) used the GPU **without the solver lock**. It wrote no results. Later CPU-only runs used
`CUDA_VISIBLE_DEVICES=-1`, and every intended GPU run went through `scripts/ops/gpulock_run.py b6`.

## 3. Clean install, Windows (run 2026-11-08)

- Build: `python -m build` is not available in the amm env, so the wheel was built with
  `python -m pip wheel . --no-deps` from a clean copy of `pyproject.toml`, `README.md`, `amm/` and `tests/` under
  `C:\AI\AgenticMetamaterials_workspaces\b6\src`. Wheel build 13 s (isolated, setuptools from PyPI). The sdist was
  built with `setuptools.build_meta.build_sdist`.
  - Wheel `amm-0.2.0-py3-none-any.whl` (97,568 B, sha256 `9f7411b6...0572`): `amm/*.py` and
    `data_manifest.json`. No data files and no `app/`, as intended.
  - A rebuild after the final pyproject and README edits gave the same file list (98,309 B; only the description
    differs).
- venv: Anaconda base Python 3.11.5 (the project env is 3.10.18), `python -m venv`, in 7 s.
- The user's pip configuration adds an extra index (`pypi.ngc.nvidia.com`) that does not resolve here, so every
  package retried five times. The first two attempts were stopped, and `--isolated` does not drop that setting.
  The clean install used `PIP_CONFIG_FILE=nul` (no pip config files at all, PyPI only). This is a machine setting,
  not a packaging problem.
- `pip install "amm-0.2.0-py3-none-any.whl[all]"`: **136 s, success**, 1.7 GB venv. `[test]` added pytest in 7 s.
- Smoke check: `import amm` gives 0.2.0 from site-packages and MKL CBWR 65538; torch 2.15.0+cpu, CUDA False.
- CPU test subset (`pytest -m "not gpu"`, run from a copy of `tests/` plus `pyproject.toml` outside the checkout,
  so the installed wheel is tested):
  - first run, with the initial conftest: 86 passed, 7 skipped, 1 deselected, 0 failed, in 474 s;
  - final conftest: **90 passed, 3 skipped (data), 1 deselected (gpu), 0 failed** in 442 s.
  - `test_app.py`, `test_app_live.py`, `test_bench.py` and `test_harness.py` are not collected there, because they
    need `app/`, `scripts/bench/`, `bench/v1` and the data. The slowest test on CPU is the adversarial-k mutation
    test, at 115 s.
- Tutorials (a) and (c) and the MCP probe ran in the venv (section 2).
- Data behaviour checked in the venv (copy of the 4 runtime files in `b6\amm-data-1`, PA12 request):

| Setting | check_bounds | atlas_suggest | search (budget 8) |
|---|---|---|---|
| no data | UNAVAILABLE / UNAVAILABLE | error "no atlas at nu_s = 0.39 (atlases: 0.3, 0.342, 0.39)" | "internal error: FileNotFoundError ... error_model.json" |
| `AMM_DATA_DIR` set | UNAVAILABLE / UNAVAILABLE (**bug B6-1**) | same error | runs, not atlas-seeded, found false, 91 s |
| `AMM_DATA_DIR` + `tools.ATLAS_DIR = data.data_dir()` | FEASIBLE / FEASIBLE | sphere_ligaments c 0.12, w 0.1817 | atlas-seeded, found true, 23 s |

- A FutureWarning (`torch.jit.script` is deprecated) comes from botorch and gpytorch under torch 2.15. It is
  harmless.
- **The venv `C:\AI\AgenticMetamaterials_workspaces6_venv` was deleted after the tests** (2026-11-08), together
  with the temporary test and checkout copies. Kept in `...6\`: the dist folders, the logs and the freeze.

### pip freeze (clean venv)

```
amm @ file:///C:/AI/AgenticMetamaterials_workspaces/b6/dist/amm-0.2.0-py3-none-any.whl#sha256=9f7411b6c5fa5443a3211a939ca7b881fd30a4cd68fc214a16af4a8533990572
annotated-types==0.8.0
anyio==4.16.0
attrs==26.1.0
botorch==0.18.1
cffi==2.1.1
click==8.5.1
cloudpickle==3.1.2
cryptography==50.0.2
filelock==4.2.9
fsspec==2026.9.0
gpytorch==1.15.2
h11==0.16.0
httpcore2==2.16.0
httpx2==2.16.0
idna==3.20
ImageIO==2.38.1
intel-cmplr-lib-ur==2026.2.0
intel-openmp==2026.2.0
Jinja2==3.1.6
joblib==1.6.0
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
lazy-loader==0.6
linear_operator==0.6.1
MarkupSafe==3.0.4
mcp==2.3.0
mcp-types==2.3.0
mkl==2026.2.0
mpmath==1.3.0
multipledispatch==1.0.0
mypy_extensions==1.2.0
narwhals==2.28.0
networkx==3.6.1
ninja==1.13.2
numpy==2.4.6
onemkl-license==2026.2.0
opentelemetry-api==1.45.2
packaging==26.3
pillow==13.0.0
pycparser==3.12
pydantic==2.14.3
pydantic_core==2.50.4
PyJWT==2.15.1
pypardiso==0.4.7
pyre-extensions==0.0.32
python-multipart==0.0.33
pywin32==312
referencing==0.37.0
rpds-py==2026.9.1
scikit-image==0.26.0
scikit-learn==1.9.1
scipy==1.17.1
sse-starlette==3.7.0
starlette==1.10.0
sympy==1.14.0
tbb==2023.2.0
tcmlib==1.6.0
threadpoolctl==3.8.0
tifffile==2026.3.3
torch==2.15.0
truststore==0.10.5
typing-inspect==0.9.0
typing-inspection==0.4.5
typing_extensions==4.16.0
umf==1.2.0
uvicorn==0.54.0
(+ pytest 9.x and its dependencies from the [test] extra, installed afterwards)
```

## 3b. Clean install, Linux container (run 2026-11-08)

The coordinator relayed the user's approval of this test ("yes approved") during B6. Only `python:3.12-slim` was
pulled: 5 s, digest `python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`, image id
`sha256:78976a69c067...`, 119 MB. The image is kept.

- `docker run --rm --name amm_b6_linux --cpus 8 --memory 16g`, no GPU passthrough.
  - Mounts: `...6\linux_in` read-only as `/in` (the final wheel from `dist2`, sha256 `8f8741ef...ae33`, plus
    `tests/`, `pyproject.toml`, `examples/*.py` and `run_linux.sh`), and `...6\linux_out` as `/out` (logs).
  - The container was removed by `--rm` (checked with `docker ps -a`: none).
- Platform: Debian 13 (trixie), Python 3.12.16, kernel 6.18.54.1-microsoft-standard-WSL2 (Docker Desktop on this
  machine), with `nproc` 32 inside (the `--cpus` quota is not a cpuset), and `MKL_NUM_THREADS=8`.
- Installs: CPU torch from the PyTorch CPU index, `torch 2.15.0+cpu`, 31 s; then the wheel `[all]` and
  `pytest>=9.0` from PyPI, 41 s. The image's pip had no extra-index configuration.
- Smoke check: amm 0.2.0 from `/usr/local/lib/python3.12/site-packages`, CUDA False, MKL CBWR 65538.
- Tutorial (a): 14 s, evaluate 12.6 s, checks passed. The log is `examples/outputs/01_evaluate_tensor_linux_docker_cpu.log`;
  the tensor matches the Windows GPU run except the sign of two printed zeros, and E100 = 0.09541189920967831,
  the same as the Windows CPU venv. Tutorial (c): 17 s, same verdicts. MCP probe: 1 s.
- Tests, `-m "not gpu"`: **90 passed, 3 skipped (data), 1 deselected (gpu), 0 failed** in 360 s. Warnings: the
  `torch.jit.script` FutureWarning, and scikit-image marching cubes under NumPy 2.5 ("setting the shape on a
  NumPy array has been deprecated").
- Total in the container: 467 s.

### pip freeze (Linux container)

```
amm @ file:///in/amm-0.2.0-py3-none-any.whl#sha256=8f8741ef27a833e99e346f5901404b99db02e5116932c3e2c62b83eae397ae33
annotated-types==0.8.0
anyio==4.16.0
attrs==26.1.0
botorch==0.18.1
cffi==2.1.1
click==8.5.1
cloudpickle==3.1.2
cryptography==50.0.2
filelock==4.2.4
fsspec==2026.9.0
gpytorch==1.15.2
h11==0.16.0
httpcore2==2.16.0
httpx2==2.16.0
idna==3.20
ImageIO==2.38.1
iniconfig==2.3.1
intel-cmplr-lib-ur==2026.2.0
intel-openmp==2026.2.0
Jinja2==3.1.6
joblib==1.6.0
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
lazy-loader==0.6
linear_operator==0.6.1
MarkupSafe==3.0.3
mcp==2.3.0
mcp-types==2.3.0
mkl==2026.2.0
mpmath==1.3.0
multipledispatch==1.0.0
mypy_extensions==1.2.0
narwhals==2.28.0
networkx==3.7
ninja==1.13.2
numpy==2.5.4
opentelemetry-api==1.45.2
packaging==26.3
pillow==13.0.0
pluggy==1.7.0
pycparser==3.12
pydantic==2.14.3
pydantic_core==2.50.4
Pygments==2.21.0
PyJWT==2.15.1
pypardiso==0.4.7
pyre-extensions==0.0.32
pytest==9.2.0
python-multipart==0.0.33
referencing==0.37.0
rpds-py==2026.9.1
scikit-image==0.26.0
scikit-learn==1.9.1
scipy==1.18.1
setuptools==78.1.0
sse-starlette==3.7.0
starlette==1.10.0
sympy==1.14.0
tbb==2023.2.0
tcmlib==1.6.0
threadpoolctl==3.8.0
tifffile==2026.10.15
torch==2.15.0+cpu
truststore==0.10.5
typing-inspect==0.9.0
typing-inspection==0.4.5
typing_extensions==4.16.0
umf==1.2.0
uvicorn==0.54.0
```

## 4. Packaging findings

Fixed in `pyproject.toml`:

- No `readme`, so the wheel had no long description. Added `readme = "README.md"`
  (`Description-Content-Type: text/markdown`).
- Pytest markers registered (`gpu`, `data`, `repo`, `slow`), so `-m "not gpu"` works without unknown-marker
  warnings.

Checked and correct: core and extras metadata (Requires-Dist and Provides-Extra as documented),
`data_manifest.json` in the wheel, and `all`/`test` resolving to search + mcp + gui + export.

Not fixed (outside the allowed edits; open):

- **B6-1 (amm bug)**: `amm/tools.py` line 55, `ATLAS_DIR = Path(__file__).resolve().parents[1] / "results" /
  "atlas"`, ignores `AMM_DATA_DIR`. An installed wheel never finds the atlas through the documented variable.
  Suggested fix: `ATLAS_DIR = amm.data.data_dir()`, evaluated at call time. A related point:
  `atlas.ERROR_MODEL_PATH` is frozen at import.
- **B6-2 (amm, message)**: `atlas_suggest` and `check_bounds` say "no atlas at nu_s = 0.39 (atlases: 0.3, 0.342,
  0.39)" when the file is missing. They should name the missing file or directory and `AMM_DATA_DIR`.
- **B6-3 (amm, message)**: `search` without `error_model.json` returns "internal error: FileNotFoundError". It
  should return a ToolError that names the data set.
- **sdist**: the setuptools default includes `tests/test_*.py` but not `tests/conftest.py`, `docs/` or
  `examples/`. A `MANIFEST.in` is needed (left for B7, because the file is outside the allowed edits).
- **GUI not in the wheel**: the `gui` extra installs only starlette and uvicorn, and `app/` and `web/dist` are
  source-tree only. This is documented in `docs/gui.md`. Whether to ship the GUI as a package is a B7 decision.

## 5. Tests and CI

`tests/conftest.py` adds markers per test or module from one table (`NEEDS`). A test is skipped with the reason
when its requirement is absent:

- the data files, at the paths amm actually reads (`tools.ATLAS_DIR`, `atlas.ERROR_MODEL_PATH`);
- source-checkout paths;
- CUDA.

`test_app*.py`, `test_bench.py` and `test_harness.py` are not collected when their module-level imports would
fail, and the report header names the reason. The marks were found empirically, not guessed:

- **Installed wheel, no repo files:** first run 86 passed, 0 failed. Removing the `data` marks of `test_outcomes`
  showed that only 2 of the 6 guessed tests need the atlas, so the other 4 marks were dropped.
- **Checkout simulation without `results/atlas`** (copy of the checkout without `results/atlas` and
  `results/verification`, `-m "not gpu and not slow"`): before the marks, 8 failures (7 in `test_app.py`, which
  mirrors atlas rows, and `test_harness::test_plan_writes_manifest_with_full_identity`); with the marks, 97 passed,
  22 skipped, 0 failed. `test_bench.py` imports `scripts/bench/build.py`, which loads the error model at import,
  so that module needs the data at collection.
- `slow`: tests above about 10 s in the CPU-only run: the certificate ladders, the mutation tests, and the 3
  `test_tools` replay tests (30 s each on CPU, 3 s with CUDA).

CI (`.github/workflows/ci.yml`) is **not run**: there is no remote, and none was created or pushed. On each OS it
does the following:

1. installs CPU-only torch from the PyTorch CPU index, then `.[test]`;
2. prints the environment;
3. runs `python docs/gen_tool_reference.py --check`;
4. runs `pytest -q -m "not gpu" -rs`;
5. runs tutorial (a).

The YAML was parsed (PyYAML), and every step's command was run locally on Windows. Coverage depends on what is
committed. With `results/atlas` (47 MB) and `results/bench` in the repository, the CI subset is every test except
the GPU tests. Without them, the `data` and `repo` tests are skipped and reported, which is the 90+ test subset
of section 3.

## 6. Final suite (amm env)

`python scripts/ops/gpulock_run.py b6 -- python -m pytest -q -rs -p no:cacheprovider` (amm env, RTX 4090, solver
lock held): **151 passed, 0 skipped, 0 failed** in 274 s (wall time 277 s).

- 151 tests includes the GUI tests that another agent added in the meantime (`tests/test_app.py`, now 18 tests,
  and `tests/test_app_live.py`).
- With every requirement present, the conftest skips nothing, so the full suite runs as before B6 (144 at the end
  of B1-B3).
- `docs/gen_tool_reference.py --check`: up to date, 17 tools, frozen contract identical.

## 7. Open items

- Linux: tested only in a WSL2 container (section 3b). Native Linux will first run in CI.
- NumPy 2.5 deprecation in scikit-image marching cubes (Linux freeze): harmless now, but watch it at the next
  NumPy release.
- The CI workflow has never run on GitHub (no remote). The first push will be its first run. The ubuntu job
  is the first native Linux run (the container run in section 3b was under WSL2).
- B6-1, B6-2 and B6-3 need an `amm/` edit. That edit changes `code_hash()` but not `checker_hash()`, because
  `tools.py` is not a checker file. Check this when the fix is made.
- Notebooks (`.ipynb`) wait for nbformat or jupyter in an environment.
- `MANIFEST.in`, the licence, the Zenodo DOI and the citation: B7.
- The plan's "local GPU test log": the final suite in section 6 is that log, with the GPU tests included.
