# Installation

amm is a pure-Python package (`amm-0.2.0-py3-none-any.whl`). It needs Python >= 3.10 on x86-64 Windows or Linux,
because PARDISO comes from Intel MKL through `pypardiso`. There is no PyPI release yet. Install from a wheel built
from the source tree, or from the checkout.

## 1. Core

```
python -m venv .venv
.venv\Scripts\activate            # Linux: source .venv/bin/activate
python -m pip install dist/amm-0.2.0-py3-none-any.whl
```

To build the wheel and sdist from a checkout, run `python -m pip wheel . --no-deps -w dist`. If the `build`
package is installed, `python -m build` also works. For development, install editable with
`python -m pip install -e ".[test]"`.

Core dependencies: `numpy>=2.2`, `scipy>=1.15`, `pypardiso>=0.4.7`, `mkl`, `torch>=2.5`, `pydantic>=2.14`. The core
gives every tool except `search` (Bayesian optimization) and the MCP transport: specification, bounds,
`evaluate`, `certify`, as-built, screening, export, submit and replay. The atlas-based parts of `check_bounds`,
`atlas_suggest` and `search` also need the data files ([data.md](data.md)).

Check the installation:

```
python -c "import amm; print(amm.__version__, amm.MKL_CBWR_STATUS)"     # 0.2.0 65538
python examples/01_evaluate_tensor.py                                   # tutorial (a), about 5-20 s
```

`65538` means MKL runs in conditional-numerical-reproducibility mode (AUTO|STRICT), which exact replay relies on.

## 2. Optional extras

| Extra | Installs | Enables |
|---|---|---|
| `search` | botorch >= 0.14, gpytorch >= 1.14 | the `search` tool. Without it, `search` returns "amm.search (the `search` tool) needs BoTorch ... pip install amm[search]". |
| `mcp` | mcp >= 2.3 | `python -m amm.mcp_server` ([mcp.md](mcp.md)) |
| `gui` | starlette >= 1.7, uvicorn >= 0.54 | the dependencies of the browser GUI. The GUI code itself (`app/`, `web/`) is in the source tree only ([gui.md](gui.md)). |
| `export` | scikit-image >= 0.25 | marching-cubes STL surfaces. Without it, `export` writes the voxel boundary surface (method `voxel_faces`). |
| `all` | search + mcp + gui + export | |
| `test` | pytest >= 9.0 + all | the test suite |
| `gpu` | cupy-cuda12x | not used by amm. It is for GPU scripts outside the package. |
| `verify` | scikit-fem >= 12.0.2 | the third-party FE cross-check script (`scripts/verify/skfem_check.py`) |

```
python -m pip install "dist/amm-0.2.0-py3-none-any.whl[all]"
```

## 3. CPU only or CUDA

amm uses PyTorch for the search-tier band solver and for the certificate's adversarial k search. Static
homogenization always runs on the CPU (PARDISO).

- **CPU only.** On Windows, the PyPI torch wheel is CPU-only (`torch 2.15.0+cpu` in the clean install below). On
  Linux, the PyPI wheel brings the CUDA libraries (several GB). Install the CPU build first with
  `python -m pip install torch --index-url https://download.pytorch.org/whl/cpu`, then install amm. Without CUDA,
  `amm.bloch.resolve_device("cuda")` returns `"cpu"`. Bands are then computed on the CPU, which is slower (tutorial
  (a): 14 s instead of 2 s for one `evaluate`), and the results are not bit-identical to the GPU path.
- **CUDA.** Install a CUDA build of torch before amm, for example
  `python -m pip install torch --index-url https://download.pytorch.org/whl/cu124`. All project results used
  `torch 2.5.1+cu124` on an RTX 4090. `evaluate` then uses the GPU automatically. Check with
  `python -c "import amm, torch; print(torch.cuda.is_available())"`. Note the order: `import amm` first, then torch.

## 4. Threads and environment

| Variable | Default | Meaning |
|---|---|---|
| `MKL_NUM_THREADS` | 16 (set by `import amm` if unset) | PARDISO threads. Use the number of physical cores. |
| `MKL_CBWR` | `AUTO,STRICT` (set by `import amm` if unset) | bit-reproducible MKL. Do not change it if you need exact replay. |
| `AMM_DATA_DIR` | unset | folder with the atlas and error-model files ([data.md](data.md); note bug B6-1) |
| `AMM_ALLOW_TORCH_FIRST` | unset | `1` skips the check that MKL initializes before torch (not recommended) |

## 5. Tests

```
python -m pytest -q                    # full suite in a checkout (GPU tests run if CUDA is present)
python -m pytest -q -m "not gpu"       # the CI subset
python -m pytest -q -m "not slow"      # quick subset (skips the certificate ladders)
```

`tests/conftest.py` marks tests `gpu`, `data`, `repo` and `slow`. It skips, with the reason, every test whose
requirement is absent: a CUDA device, the data files where amm reads them, or source-checkout files outside the
package (`app/`, `bench/`, `scripts/bench/`, `results/`). The full suite has 144 tests and took 275 s on the
development machine (i9-13900KF, RTX 4090).

## 6. Clean-install test, Windows (run 2026-11-08)

Run on Windows 11, with a fresh venv from the Anaconda base Python 3.11.5 (the project's own env is 3.10), outside
the checkout. All pip configuration files were disabled (`PIP_CONFIG_FILE=nul`), so only PyPI was used:

```
python -m venv C:\AI\AgenticMetamaterials_workspaces\b6_venv
set PIP_CONFIG_FILE=nul
b6_venv\Scripts\python -m pip install --no-cache-dir "amm-0.2.0-py3-none-any.whl[all]"    # 136 s
b6_venv\Scripts\python -m pip install --no-cache-dir "amm-0.2.0-py3-none-any.whl[test]"   # 7 s (adds pytest)
```

Resolved versions (pip freeze; the full list is in `results/software/NOTES_B6.md`): torch 2.15.0+cpu,
numpy 2.4.6, scipy 1.17.1, pypardiso 0.4.7, mkl 2026.2.0, pydantic 2.14.3, botorch 0.18.1, gpytorch 1.15.2,
mcp 2.3.0, starlette 1.10.0, uvicorn 0.54.0, scikit-image 0.26.0. The tests and tutorials run there, their
timings and the issues found are in `results/software/NOTES_B6.md`.

## 7. Clean-install test, Linux (run 2026-11-08)

Run in a throwaway Docker container from `python:3.12-slim`, with image digest
`python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`. The image is Debian 13,
Python 3.12.16, running under Docker Desktop's WSL2 kernel 6.18 on the development machine, without GPU
passthrough. The container ran with `--cpus 8 --memory 16g`, and `--rm` removed it afterwards. The wheel, tests
and examples were mounted read-only, and the tests ran from a copy without `amm/`, `results/` or `scripts/`, so
they exercised the installed wheel:

```
docker pull python:3.12-slim
docker run --rm --cpus 8 --memory 16g -v <in>:/in:ro -v <out>:/out -w /work python:3.12-slim bash /in/run_linux.sh
# inside run_linux.sh:
cp -r /in/tests /in/pyproject.toml /in/examples /work/
python -m pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu      # 31 s
python -m pip install --no-cache-dir "/in/amm-0.2.0-py3-none-any.whl[all]" "pytest>=9.0"        # 41 s
python -m pip freeze
MKL_NUM_THREADS=8 python examples/01_evaluate_tensor.py
MKL_NUM_THREADS=8 python -m pytest -q -m "not gpu" -rs -p no:cacheprovider tests
```

Result: **all steps succeeded**.

- **torch build**: CPU (`torch 2.15.0+cpu` from the PyTorch CPU index). CUDA False. MKL CBWR 65538: the pip
  `mkl` and `pypardiso` wheels load in the slim image, and MKL and torch coexist.
- **Resolved versions**: numpy 2.5.4, scipy 1.18.1, pypardiso 0.4.7, mkl 2026.2.0, intel-openmp 2026.2.0,
  pydantic 2.14.3, botorch 0.18.1, gpytorch 1.15.2, mcp 2.3.0, starlette 1.10.0, uvicorn 0.54.0, scikit-image
  0.26.0, pytest 9.2.0 (70 packages; the full freeze is in `results/software/NOTES_B6.md`).
- **Tutorials**: (a) 14 s (evaluate 12.6 s on CPU). The printed tensor equals the GPU run on Windows to the printed
  digits, except the sign of two printed zeros. (c) 17 s. The MCP probe took 1 s.
- **Tests**: `-m "not gpu"` gave **90 passed, 3 skipped, 1 deselected, 0 failed** in 360 s. The 3 skips are the
  `data` tests: the atlas is not in the wheel. The `app`, `bench` and `harness` modules are not collected outside a
  checkout. The warnings are deprecation notices from torch (`torch.jit.script`) and scikit-image under NumPy
  2.5.
- **Total container time**: 467 s.

This is a WSL2 container on a Windows host, not a native Linux machine. The CI job on ubuntu-latest will be the
first native Linux run.
