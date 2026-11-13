# AMM: AgenticMetamaterials (Python package `amm`)

Certified design of periodic mechanical and phononic metamaterial unit cells, by script, by an LLM agent over MCP,
or in a browser GUI.

AMM turns a request such as "PA12, 10 mm cells, E100 >= 25 MPa, solid fraction <= 0.25" or "a complete band gap
from 20 to 26 kHz" into a released design, a refusal backed by evidence, or a question. A release needs a solver
certificate that the agent cannot write. A refusal must cite a record held in the session: a violated rigorous
bound, a bounded search that found nothing, or an undetermined certificate. Every call is logged and can be
replayed exactly without an LLM.

Version 0.2.0 (tool contract `amm-tools/3`, outcome schema `amm-outcome/1`, data set `amm-data/1`).

## Features

- **Cell families**: TPMS (gyroid, Schwarz P, diamond, IWP; sheet or network), strut lattices (sc, bcc, octet,
  with optional node spheres) and mass-in-frame resonators (cube_bars, sphere_ligaments). The geometry uses
  finite-cell partial voxels.
- **Targets**: solid fraction, E100, shear modulus G, bulk modulus, Poisson ratio nu100 (minimum or maximum), and
  complete elastic-wave band-gap intervals, in physical units (Pa to GPa, Hz to MHz) or normalized units.
- **Search tier**: periodic homogenization (PARDISO) with the full 6x6 tensor C* and derived quantities (cubic
  constants, Zener ratio, directional moduli), band diagrams (PyTorch, GPU or CPU), a precomputed search atlas
  of 2,722 cells per solid Poisson ratio with a calibrated error model, and Bayesian optimization (BoTorch).
- **Acceptance tier**: certificates with a guarded three-resolution static ladder over five grid phases, band-gap
  checks by inertia counts with an edge-convergence guard and an adversarial k search, and an as-built
  erode/dilate robustness flag. The verdict is certified, refuted or undetermined.
- **Physics bounds** before any search: Voigt, cubic stability, consistency, and the rule that a gap cannot
  contain f = 0 (Hashin-Shtrikman is advisory).
- **Outcomes**: five outcomes (certified candidate, refuted candidate, proven infeasible, not found in families,
  numerically undetermined) plus "information needed", each with an evidence card.
- **Tool contract**: 17 typed, validated, logged tools (`amm.tools.Session`); exact LLM-free replay; versioned
  schemas.
- **MCP server** (`python -m amm.mcp_server`) for Claude Code, Codex CLI or any MCP client.
- **Browser GUI** (source checkout; `app/`, `web/`).
- **Manufacturing screening and export**: minimum feature against a printer limit, tiled connectivity,
  watertight single-cell and tiled STL, and `report.json` with the evidence. This is screening, not a printability
  claim.

## Install

```
python -m pip wheel . --no-deps -w dist
python -m pip install "dist/amm-0.2.0-py3-none-any.whl[all]"
python examples/01_evaluate_tensor.py
```

AMM needs Python >= 3.10 on x86-64 Windows or Linux (Intel MKL). A GPU is optional. The extras `search`, `mcp`,
`gui`, `export` and `test`, CPU-only and CUDA installs, and the data files are covered in
[docs/install.md](docs/install.md) and [docs/data.md](docs/data.md).

## Quick start

```python
import amm                      # import amm before torch
from amm import tools

s = tools.Session("my_session", profile="C")
s.call("set_material", {"name": "PA12"})
s.call("set_constraints", {"cell_size": 10, "cell_size_unit": "mm"})
s.call("set_target", {"E100_min": {"value": 25, "unit": "MPa"}, "density_max": 0.25})
best = s.call("atlas_suggest", {"top": 3})["result"]["best"]
cert = s.call("certify", {"design": best[0]["design"]})["result"]
print(cert["verdict"])                                          # certified
print(s.call("submit", {"decision": "release", "design": best[0]["design"]})["result"]["outcome_card"]["outcome"])
```

More in [docs/quickstart.md](docs/quickstart.md) and the tutorials in [examples/](examples/):

1. evaluate a cell and read its tensor;
2. go from the atlas to a certificate;
3. export and manufacturing screening;
4. an MCP client probe.

## Documentation

[Index](docs/index.md):

- [install](docs/install.md)
- [quick start](docs/quickstart.md)
- [concepts](docs/concepts.md)
- [tool contract](docs/tool_contract.md)
- [MCP](docs/mcp.md)
- [GUI](docs/gui.md)
- [extending](docs/extending.md)
- [data](docs/data.md)
- [limitations](docs/limitations.md)

## Tests

```
python -m pytest -q                 # 144+ tests; GPU tests run when CUDA is present
python -m pytest -q -m "not gpu"    # CPU subset, as in CI (.github/workflows/ci.yml)
```

## Repository layout

| Path | Contents |
|---|---|
| `amm/` | the package: geometry, FEM, homogenization, Bloch, certificates, bounds, atlas, search, tool contract, MCP server, export |
| `app/`, `web/` | GUI backend (Starlette) and front end |
| `docs/`, `examples/` | documentation and tutorials (with recorded outputs) |
| `tests/` | test suite |
| `bench/` | the simulator-graded benchmark briefs (`bench/v1`) |
| `scripts/` | atlas, calibration, benchmark, verification and software scripts |
| `results/` | recorded results and notes per work package (`results/*/NOTES.md`) |
| `paper/figures/`, `paper/tables/` | rendered figures and tables of the paper |
| `plan/`, `research/`, `external/` | local working material (plans, literature notes, a clone of a public MIT registry repository); not part of a release |

This project is independent of AgenticTO (see `00_INDEPENDENT_PROJECT__NOT_AgenticTO.md`).

## Citation

The accompanying article is S. Yang and J. Wang, "Selecting and verifying load-bearing periodic cells for
elastic-wave band gaps with numerical acceptance checks", [arXiv:2611.14796](https://arxiv.org/abs/2611.14796) (2026).

`CITATION.cff` holds the citation metadata of AMM 0.2.0 and the accompanying article. Release v0.2.0 carries the
wheel, the sdist and the data assets `amm-data-1.zip` (search atlas, error model) and `amm-results-archive.zip`
(engineering-case exports).

## Licence

BSD 3-Clause (`LICENSE`). Third-party licences of the dependencies and of the JavaScript bundled in `web/dist` are
listed in `LICENSES.md` and `THIRD_PARTY_NOTICES.txt` of a release. The data set amm-data/1 and the results archive
are release assets under CC BY 4.0.
