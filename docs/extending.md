# Extending amm

amm 0.2.0 has no plug-in registry. Cell families and target types are defined in several modules, and the tool
contract, the certificate identity and the benchmark all depend on them. This page has three parts:

1. what works today with no code change (homogenizing your own voxel geometry);
2. the checklist for adding a family;
3. the checklist for adding a target type.

Any change to `amm/` changes `amm.tools.code_hash()` and, for solver modules, `certify.checker_hash()`. After
that, old session logs no longer replay as current code, and old certificates are no longer current. This is
intended, so that a certificate is always tied to the code that checked it. Record the old identities before you
edit, and run the full test suite afterwards.

## 1. Homogenize your own geometry (no code change)

The homogenization and band solvers take any voxel mask or coverage field. The snippet below computes C* of a
cell made of three orthogonal plates. It was run for this page; the output is shown below it.

```python
import numpy as np
import amm  # before torch
from amm import fem, homog, tensor

n = 24
x = (np.arange(n) + 0.5) / n
X, Y, Z = np.meshgrid(x, x, x, indexing="ij")
t = 0.06  # half thickness of three orthogonal plates through the cell centre (cell units)
mask = (np.abs(X - 0.5) < t) | (np.abs(Y - 0.5) < t) | (np.abs(Z - 0.5) < t)
r = homog.homogenize(mesh=fem.build_mesh(mask, nu=0.3))
print(f"density {r['density']:.3f}  E100 {r['E100']:.4f}  G {r['G']:.4f}  zener {r['zener']:.3f}")
print("E111 from the full tensor:", round(tensor.summary(r["C"])["E111"], 4))
```

```
density 0.230  E100 0.1699  G 0.0345  zener 0.472
E111 from the full tensor: 0.0911
```

This gives search-tier-like numbers for any geometry. It does **not** give a certificate. `certify`, the atlas and
the tools work only on the built-in families, because the certificate re-voxelizes the design at several
resolutions and grid phases from its parametric definition. A binary mask has no such definition.

## 2. Add a cell family or kind

A *kind* is a parametric shape, for example `cube_bars`. A *family* groups kinds that share a parameter box and
an error model, for example `resonator`. To add a kind to an existing family, or a new family:

| Step | Where | What |
|---|---|---|
| 1 | `amm/geometry.py` | add the kind to `TPMS`, `STRUTS` or `RESONATORS` (or a new tuple plus an entry in `FAMILIES`). Add its level-set function to `field()`: solid where phi <= threshold, coordinates in cell units, periodic and cubic-symmetric. Use the explicit `shift` argument so grid phases work. |
| 2 | `amm/atlas.py` | add its parameter box to `BOX` and its validity rule to `valid()`, so the shape is what its name says. For a new family, add `FEATURE_PARAM` (the parameter that sets the thinnest feature) and a block in `grid_specs()`. |
| 3 | `amm/tools.py` | add the kind to the `Kind` literal (and the family to `Family`), document its parameters in `Design`, add the rule text in `list_families`, and add the family to the default `families` in `Session.__init__`. These are contract changes: bump `SCHEMA_VERSION` and extend `project()` so older logs still replay. |
| 4 | data | run the atlas for each solid Poisson ratio (`python scripts/atlas/run_atlas.py 0.3`, and so on), then calibrate the error model for the new family (`scripts/atlas/calibrate.py`, `scripts/atlas/extend_calibration.py`) and regenerate the data manifest (`scripts/software/make_data_manifest.py`). Until then, `atlas.oracle` leaves the new family out, because only rows inside the calibrated domain (`error_domain`) count, and `search` reports `calibrated_domain: false`. |
| 5 | verification | percolation and density at several resolutions (as in `tests/test_core.py::test_density_matched_across_resolutions`), the bounds-soundness test (`tests/test_bounds.py`), and certificate behaviour on clean and seeded-fault cells (`tests/test_mutations.py`). |
| 6 | mirrors | the GUI backend mirrors family boxes, rules and preview geometry (`app/toolspec.py` parses them from the amm source, and `app/geom.py` and `app/physics.py` repeat the formulas). The benchmark prompt text in `amm/bench.py` lists the families. |

The certificate code (`amm/certify.py`) needs no change for a new kind. It works on any spec that
`geometry.design_cell` can voxelize.

## 3. Add a target type

The supported targets are the keys of `certify.STATIC_KEYS` (density, E100, G, bulk, nu100; minimum or maximum)
and `gap`. To add a static target, for example a minimum on E111:

| Step | Where | What |
|---|---|---|
| 1 | `amm/homog.py` / `amm/tensor.py` | make sure the quantity is computed from C* for every solve. Today `homogenize` returns density, E100, G, bulk, nu100, C11, C12, C44, zener and cubic_deviation. `tensor.summary` (E110, E111, the Voigt and Reuss averages) is called only by `evaluate`. |
| 2 | `amm/certify.py` | add the target key to `STATIC_KEYS` (quantity, `"min"` or `"max"`), the quantity to `STATIC_QUANTITIES` (so the static block extrapolates and guards it) and, if it converges from above like stiffness, to `FROM_ABOVE`. `_static_row` drops C* (`r.pop("C")`) after the solve, so the quantity must already be a key of the `homogenize` result (for example, computed in `homog.cubic_constants`). |
| 3 | `amm/units.py` | normalize it in `normalize()` (add it to `STIFFNESS_KEYS` if it is a modulus) and convert it back in `to_physical()`. |
| 4 | `amm/bounds.py` | add a rigorous bound if one exists (for any directional Young's modulus, Voigt V1 gives E(n) <= phi E_s). A bound must never refute an achievable design; extend `tests/test_bounds.py`. |
| 5 | `amm/atlas.py` and the error model | `slacks()` iterates over `STATIC_KEYS`, so the atlas and search see the new key once the atlas rows carry the quantity (they keep the tensor only if it was stored, so the atlas may need to be recomputed). Calibrate an error range for it, otherwise `err_for` has none and the search tier treats it as exact. |
| 6 | `amm/tools.py` | add the argument to `set_target` (and to the `ClarifyOption.set` description), bump `SCHEMA_VERSION` and extend `project()`. |
| 7 | mirrors and benchmark | `app/physics.py` and `app/backend.py` mirror `normalize` and `set_target`. The benchmark (`amm/bench.py`, `scripts/bench/`) lists the target keys. |

A new kind of *dynamic* target, for example a directional or partial gap, also needs a new Bloch block in
`amm/certify.py` and `amm/bloch.py` with its own convergence guard. It cannot be added through `STATIC_KEYS`.

After either change, regenerate the contract reference (`python docs/gen_tool_reference.py`) and the frozen
contract (`python scripts/software/write_contract.py`), then run the full test suite.
