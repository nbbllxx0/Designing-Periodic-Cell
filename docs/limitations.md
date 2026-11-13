# Limitations

What amm 0.2.0 does not do, or does only in part. Each item is a property of the current code. Items marked
**bug** are open defects in `amm/`, reported in `results/software/NOTES_B6.md` and not yet fixed.

## Physics and scope

- Linear elasticity, small strain, one isotropic solid plus void. No plasticity, buckling, large deformation,
  damping, viscoelasticity, fluid loading, thermal or acoustic-fluid physics.
- Cubic-symmetric cell families only: four TPMS kinds (gyroid, Schwarz P, diamond, IWP; sheet or network), three
  strut lattices (sc, bcc, octet, with optional node spheres) and two mass-in-frame resonators (cube_bars,
  sphere_ligaments). Every family has 1-2 parameters in a fixed box (`list_families`).
- Targets: density, E100, G (C44), bulk, nu100 and complete-gap intervals. Zener ratio, E110, E111, directional
  stiffness, the Voigt and Reuss averages and partial (polarization- or direction-limited) gaps are outputs only.
  They cannot be targeted or certified.
- Gaps are for the infinite periodic lattice. Finite blocks, boundaries, mounting, transmission and damping are
  not modelled.

## Certificates

- They are acceptance tests under stated discretization, sampling and guard assumptions, not continuum theorems.
  See [concepts](concepts.md#what-a-certificate-guarantees-and-what-it-does-not).
- Thin features (thin TPMS sheets, thin struts, narrow resonator ligaments) converge slowly. The certificate then
  climbs to finer rungs (minutes), and it can end `undetermined` near the target.
- A certificate is valid only for the checker code that computed it (`certify.checker_hash()`). After any change
  to the solver code, old certificates are no longer current.

## Search tier and data

- Search-tier values are biased stiff and high in frequency by several per cent. The error model is calibrated
  only inside its domain (`atlas.error_domain`). Outside it, the oracle does not count the cell.
- The search atlas exists for solid Poisson ratios 0.3, 0.342 and 0.39 only. Any other ratio (custom materials,
  AlSi10Mg at 0.33) gives an atlas verdict of `UNAVAILABLE`.
- Without the data files, `atlas_suggest` and `search` return an error that names the missing file, where amm
  looked and how to set `AMM_DATA_DIR`; `search` does not run without the error model (no uncorrected fallback).
  See [data](data.md). (Bugs B6-1 to B6-3 of amm before B9 are fixed: the atlas now follows `AMM_DATA_DIR`.)
- The data files are distributed as a GitHub release asset, not in a DOI-minting archive.

## Hardware and platforms

- PARDISO (Intel MKL through `pypardiso`) is required. MKL wheels exist for x86-64 Windows and Linux. macOS on
  Apple silicon and other ARM machines are not supported.
- `MKL_NUM_THREADS` defaults to 16 (tuned on an i9-13900KF). On smaller machines, set it to the number of
  physical cores.
- Without CUDA, the band solver runs on the CPU. It is slower, and its results are not bit-identical to the GPU
  path. Static solves are always on the CPU.
- `import amm` must come before `import torch` (or botorch or gpytorch) in a process, because MKL's OpenMP runtime
  must initialize first. If torch is imported first, the first MKL use raises a clear `RuntimeError`.
  `AMM_ALLOW_TORCH_FIRST=1` overrides the check at your own risk.
- Exact replay (`amm.tools.replay`) is bit-exact on the machine and code that wrote the log. Across CPUs or MKL
  versions, results can differ in the last bits. A log with `export` calls replays into a temporary folder by
  default; the export result's file hashes are compared, with the logged code and checker identity written into
  the replayed report.json (code identity is not a result).

## Calls and concurrency

- Calls run one at a time. While a solve runs, the read-only tools `get_session`, `check_bounds`, `atlas_suggest`
  and `list_families` answer at once, from the session as it was when the solve started (its budget use and
  certificate are not shown until it finishes); every other call waits. Such reads are logged before the solve's
  record, so a log's records are not always in seq order (replay uses the logged numbers).
- Progress and cancel (`Session.call(..., progress=, cancel=)`, `amm.progress`) act at the solvers' checkpoints:
  a static solve, a Bloch k-point, a gap-edge solve, a search batch. A cancel takes effect at the next one (seconds
  in a certificate). A cancelled call leaves no record and no budget use; files it had already written (a
  certificate JSON, export files) are not removed. A cancel during a solve that read-only calls overlapped leaves
  its seq number unused (a gap in the log).

## Packaging

- The browser GUI (`app/`, `web/`) is not inside the wheel. The `gui` extra installs its dependencies only, so
  the GUI runs from a source checkout. See [gui](gui.md).
- The sdist is the setuptools default. It contains `amm/`, `README.md`, `pyproject.toml` and `tests/test_*.py`,
  but not `tests/conftest.py`, `docs/` or `examples/`. A `MANIFEST.in` is needed for that and was left to plan B7.
- Licences: BSD-3-Clause for the code, CC-BY-4.0 for the data (confirmed 2026-11-08). Distribution is
  GitHub release v0.2.0 (wheel, sdist and data assets); there is no DOI-minting archive.
- The `search` tool needs the `search` extra (BoTorch). The MCP server needs the `mcp` extra. Without them, these
  tools return a clear error and every other tool works.
- Linux was tested from a clean install only in a `python:3.12-slim` container under WSL2 (90 passed, 0 failed;
  [install](install.md) section 7). Native Linux will first be exercised by the CI job, which has not run yet.

## Manufacturing screening

- `screen_manufacturing` and `export` are *screening*, not printability claims. They check the minimum feature
  against a stated limit at one-voxel resolution, connectivity of a tiled block, and watertight surfaces. Support,
  powder removal, residual stress, roughness and process parameters are not checked.
- The minimum-feature estimate is conservative by about 1-2 voxels, because convex edges count as thin.
